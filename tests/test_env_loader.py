"""Guards _load_env_file()'s inline-comment handling.

A real regression: ".env" lines like "GEMINI_MODEL=gemini-2.5-flash   # note"
were loaded with the comment still attached, producing values such as
"gemini-2.5-flash   # note" that broke the Gemini API call and
SentenceTransformer model loading.
"""
from __future__ import annotations

import os

import pytest

from app.config import _load_env_file


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Point the loader at a scratch directory and clear vars it would set."""
    monkeypatch.setattr("app.config.ROOT_DIR", tmp_path)
    keys = ["FOO_MODEL", "BAR_URL", "BAZ_QUOTED", "QUX_HASHTAG"]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    yield tmp_path
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_strips_inline_comment_with_leading_whitespace(isolated_env) -> None:
    (isolated_env / ".env").write_text(
        "FOO_MODEL=gemini-2.5-flash   # override if the model ID differs\n"
    )
    _load_env_file()
    assert os.environ["FOO_MODEL"] == "gemini-2.5-flash"


def test_preserves_hash_with_no_preceding_whitespace(isolated_env) -> None:
    """Values that legitimately contain "#" (e.g. URL fragments) must survive."""
    (isolated_env / ".env").write_text("BAR_URL=https://example.com/path#section\n")
    _load_env_file()
    assert os.environ["BAR_URL"] == "https://example.com/path#section"


def test_strips_quotes_after_removing_comment(isolated_env) -> None:
    (isolated_env / ".env").write_text('BAZ_QUOTED="quoted-value"   # trailing note\n')
    _load_env_file()
    assert os.environ["BAZ_QUOTED"] == "quoted-value"


def test_value_without_comment_is_unchanged(isolated_env) -> None:
    (isolated_env / ".env").write_text("QUX_HASHTAG=plain-value\n")
    _load_env_file()
    assert os.environ["QUX_HASHTAG"] == "plain-value"
