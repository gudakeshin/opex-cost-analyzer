"""Regression tests for request_id JSON logging.

The JSON log format includes %(request_id)s, injected by _RequestIdFilter.
Logger-level filters only run for records created on that exact logger, so
records from child loggers (e.g. "opex.document_index") or third-party
libraries used to hit the root handler unfiltered and crash formatting with
KeyError: 'request_id' ("--- Logging error ---" on stderr instead of the log
line). The fix attaches the filter to the root handlers themselves.
"""

from __future__ import annotations

import io
import logging
import sys
from types import SimpleNamespace

import pytest

from app import config


@pytest.fixture
def fresh_root_logging(monkeypatch):
    """Run _configure_logging against an empty root logger (as in production).

    Under pytest the root logger already has capture handlers, which makes
    logging.basicConfig a no-op; resetting handlers/filters lets the test
    exercise the real handler created by _configure_logging. sys.stderr is
    swapped for a StringIO so both the emitted line and any
    "--- Logging error ---" output land somewhere we can read; original state
    is restored afterwards.
    """
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_filters = root.filters[:]
    saved_level = root.level
    root.handlers = []
    root.filters = []
    try:
        config._configure_logging()
        yield SimpleNamespace(stream=stream, handlers=root.handlers[:])
    finally:
        for handler in root.handlers:
            if handler not in saved_handlers:
                handler.close()
        root.handlers = saved_handlers
        root.filters = saved_filters
        root.setLevel(saved_level)


def _assert_clean_record(stream: io.StringIO, message: str) -> str:
    output = stream.getvalue()
    assert "--- Logging error ---" not in output
    assert "KeyError" not in output
    line = next((ln for ln in output.splitlines() if message in ln), None)
    assert line is not None, f"log line for {message!r} not emitted: {output!r}"
    return line


def test_opex_child_logger_formats_cleanly(fresh_root_logging):
    logging.getLogger("opex.somechild").warning('"child says hi"')
    line = _assert_clean_record(fresh_root_logging.stream, "child says hi")
    assert '"rid":"-"' in line


def test_non_opex_logger_formats_cleanly(fresh_root_logging):
    logging.getLogger("thirdparty.connector").warning('"qdrant unreachable"')
    line = _assert_clean_record(fresh_root_logging.stream, "qdrant unreachable")
    assert '"rid":"-"' in line


def test_request_id_contextvar_reaches_child_logger_records(fresh_root_logging):
    token = config.request_id_var.set("req-abc123")
    try:
        logging.getLogger("opex.document_index").warning('"indexing failed"')
    finally:
        config.request_id_var.reset(token)
    line = _assert_clean_record(fresh_root_logging.stream, "indexing failed")
    assert '"rid":"req-abc123"' in line


def test_root_handlers_carry_request_id_filter(fresh_root_logging):
    assert fresh_root_logging.handlers, "expected _configure_logging to install a root handler"
    for handler in fresh_root_logging.handlers:
        assert any(isinstance(f, config._RequestIdFilter) for f in handler.filters)


def test_configure_logging_is_idempotent_on_handler_filters(fresh_root_logging):
    config._configure_logging()
    for handler in fresh_root_logging.handlers:
        request_id_filters = [f for f in handler.filters if isinstance(f, config._RequestIdFilter)]
        assert len(request_id_filters) == 1
