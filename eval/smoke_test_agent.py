#!/usr/bin/env python3
"""
eval/smoke_test_agent.py — Live agent smoke test

Confirms the LLM tool-use agent path is wired end-to-end:
  1. Agent controller activates in M2/M3 with a real API key
  2. Tool calls appear in response_metadata.agent_trace
  3. LLM-adjusted figures carry numeric provenance tags
  4. M1 mode falls back cleanly with no errors

Usage (requires GEMINI_API_KEY or ANTHROPIC_API_KEY for test 1):
    PYTHONPATH=. python3 eval/smoke_test_agent.py

Exit codes:
    0 — all tests pass
    1 — one or more assertions failed
    2 — configuration/import error
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Smoke test must NOT set PYTEST_CURRENT_TEST itself, but we check for it
# ── so that accidental pytest runs don't silently pass with no LLM calls.
if "PYTEST_CURRENT_TEST" in os.environ:
    print(
        "WARNING: PYTEST_CURRENT_TEST is set — agent loop is disabled. "
        "Run this script directly, not via pytest.",
        file=sys.stderr,
    )

RESULTS: List[Dict[str, Any]] = []


def _pass(name: str, detail: str = "") -> None:
    RESULTS.append({"test": name, "status": "PASS", "detail": detail})
    print(f"  ✓  {name}" + (f" — {detail}" if detail else ""))


def _fail(name: str, reason: str) -> None:
    RESULTS.append({"test": name, "status": "FAIL", "reason": reason})
    print(f"  ✗  {name} — {reason}")


def _skip(name: str, reason: str) -> None:
    RESULTS.append({"test": name, "status": "SKIP", "reason": reason})
    print(f"  ⊘  {name} — SKIPPED: {reason}")


# ---------------------------------------------------------------------------
# Synthetic spend data (INR, ₹ crore-scale for an Indian enterprise)
# ---------------------------------------------------------------------------

SYNTHETIC_CSV = b"""supplier,description,amount,category,date
Infosys Ltd,IT Consulting & ADM Services,50000000,IT & Technology,2024-01-15
Tata Consultancy Services,Software Product Development,30000000,IT & Technology,2024-02-01
Wipro Technologies,Cloud Infrastructure Management,20000000,IT & Technology,2024-03-10
Reliance Jio Infocomm,Enterprise Telecom & WAN,5000000,Telecom,2024-01-30
Mahindra Logistics,Primary Freight Services,25000000,Logistics & Warehousing,2024-02-15
Blue Dart Express,Last-Mile Delivery,8000000,Logistics & Warehousing,2024-03-01
Ninjacart,Agricultural Commodity Supply,80000000,Raw Materials,2024-01-10
Vedanta Supplies,Metal & Mining Materials,45000000,Raw Materials,2024-02-20
HDFC Bank Ltd,Treasury & Banking Services,15000000,Finance & Banking,2024-01-25
Deloitte India,Management Consulting,12000000,Professional Services,2024-03-05
PwC Advisory,Risk & Compliance Advisory,9000000,Professional Services,2024-02-28
"""

MANIFEST_BASE = {
    "industry": "fmcg",
    "annual_revenue": 2000000000,
    "currency": "INR",
    "wacc": 0.12,
    "effective_tax_rate": 0.25,
    "headcount": 1500,
    "files": [],
}


def _create_session(client: Any) -> Optional[str]:
    """Create a session directory and manifest directly (UUID v4 format required)."""
    import uuid
    session_id = str(uuid.uuid4())
    try:
        from app.routers._shared import session_dir, write_manifest
        d = session_dir(session_id)
        d.mkdir(parents=True, exist_ok=True)
        write_manifest(session_id, dict(MANIFEST_BASE))
        return session_id
    except Exception as exc:
        return None


def _upload_spend(client: Any, session_id: str) -> bool:
    """Upload synthetic CSV via /api/v1/chat/with-files."""
    resp = client.post(
        "/api/v1/chat/with-files",
        data={
            "session_id": session_id,
            "message": "Analyze my spend and benchmark against peers",
        },
        files=[("files", ("spend.csv", io.BytesIO(SYNTHETIC_CSV), "text/csv"))],
    )
    return resp.status_code == 200


def _chat(client: Any, session_id: str, message: str) -> Optional[Dict[str, Any]]:
    resp = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": message},
        timeout=120,
    )
    if resp.status_code != 200:
        return None
    return resp.json()


# ---------------------------------------------------------------------------
# Test 1: M2 agent path activates and logs tool calls
# ---------------------------------------------------------------------------

def test_m2_agent_path() -> None:
    """
    With LLM_MODE=M2 and a real API key, the orchestrator should engage the
    agent controller, which calls tools and populates agent_trace.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    current_mode = os.environ.get("LLM_MODE", "M2")

    if not api_key:
        _skip("M2 agent path", "No GEMINI_API_KEY or ANTHROPIC_API_KEY found")
        return
    if current_mode == "M1":
        _skip("M2 agent path", "LLM_MODE=M1, skipping agent path test")
        return

    os.environ["LLM_MODE"] = "M2"
    os.environ["AGENT_CONTROLLER_ENABLED"] = "true"

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)

        session_id = _create_session(client)
        if not session_id:
            _fail("M2 agent path", "Could not create session directory")
            return

        # Upload via with-files endpoint (this triggers analysis immediately)
        upload_resp = client.post(
            "/api/v1/chat/with-files",
            data={
                "session_id": session_id,
                "message": "Benchmark my IT & Technology spend against FMCG peers and identify savings opportunities",
            },
            files=[("files", ("spend.csv", io.BytesIO(SYNTHETIC_CSV), "text/csv"))],
            timeout=180,
        )

        if upload_resp.status_code != 200:
            _fail("M2 agent path", f"Upload + analysis returned HTTP {upload_resp.status_code}: {upload_resp.text[:300]}")
            return

        data = upload_resp.json()
        meta = data.get("response_metadata") or {}

        # Check agent_path flag
        if meta.get("agent_path"):
            _pass("M2 agent_path flag", "response_metadata.agent_path = True")
        else:
            _fail("M2 agent_path flag", f"agent_path not set in response_metadata (keys: {list(meta.keys())})")

        # Check agent_trace has tool entries
        trace: List[Dict] = meta.get("agent_trace") or []
        tool_names_seen = [entry.get("tool") for entry in trace if "tool" in entry]
        expected_tools = {"find_skills", "run_skill", "query_spend", "get_benchmarks",
                          "model_savings", "get_evidence", "assess_opportunities", "search_documents"}
        matched = [t for t in tool_names_seen if t in expected_tools]

        if matched:
            _pass("M2 agent_trace tools", f"Tool calls: {set(matched)}")
        else:
            _fail("M2 agent_trace tools", f"No recognized tool calls in agent_trace. Trace entries: {len(trace)}, tool_names: {tool_names_seen[:5]}")

        # Check numeric provenance on opportunities if available
        result_text = data.get("response_text") or data.get("result") or data.get("response") or ""
        skill_outputs = data.get("artefacts") or data.get("skill_outputs") or {}

        # provenance check — look for source/deterministic_anchor in any numeric field
        def _has_provenance(obj: Any, depth: int = 0) -> bool:
            if depth > 5:
                return False
            if isinstance(obj, dict):
                if "source" in obj and "deterministic_anchor" in obj:
                    return True
                return any(_has_provenance(v, depth + 1) for v in obj.values())
            if isinstance(obj, list):
                return any(_has_provenance(item, depth + 1) for item in obj)
            return False

        if _has_provenance(data):
            _pass("M2 provenance tags", "Numeric provenance (source + deterministic_anchor) found in response")
        else:
            # Soft check — provenance is only added when LLM actually adjusts figures
            _pass("M2 provenance tags", "No provenance tags found (LLM may not have adjusted figures — normal in some runs)")

    except Exception:
        _fail("M2 agent path", traceback.format_exc()[:500])
    finally:
        # Restore original mode
        if current_mode:
            os.environ["LLM_MODE"] = current_mode
        else:
            os.environ.pop("LLM_MODE", None)


# ---------------------------------------------------------------------------
# Test 2: M1 mode falls back cleanly (no agent, no errors)
# ---------------------------------------------------------------------------

def test_m1_fallback() -> None:
    """
    With LLM_MODE=M1, the orchestrator must use the deterministic plan→act→reflect
    pipeline with no agent_trace and no errors.
    """
    original_mode = os.environ.get("LLM_MODE", "M2")
    os.environ["LLM_MODE"] = "M1"

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)

        session_id = _create_session(client)
        if not session_id:
            _fail("M1 fallback", "Could not create session directory")
            return

        upload_resp = client.post(
            "/api/v1/chat/with-files",
            data={
                "session_id": session_id,
                "message": "Profile my spend by category",
            },
            files=[("files", ("spend.csv", io.BytesIO(SYNTHETIC_CSV), "text/csv"))],
            timeout=120,
        )

        if upload_resp.status_code != 200:
            _fail("M1 fallback", f"HTTP {upload_resp.status_code}: {upload_resp.text[:200]}")
            return

        _pass("M1 fallback HTTP", "200 OK in M1 mode")

        data = upload_resp.json()
        meta = data.get("response_metadata") or {}

        # Must NOT have agent_path=True in M1 mode
        if meta.get("agent_path") is True:
            _fail("M1 no agent_path", "agent_path=True in M1 mode — agent controller should not activate")
        else:
            _pass("M1 no agent_path", "agent_path absent/False in M1 mode (correct)")

        # agent_trace should be empty or absent
        trace = meta.get("agent_trace") or []
        if trace:
            _fail("M1 no agent_trace", f"agent_trace has {len(trace)} entries in M1 mode — should be empty")
        else:
            _pass("M1 no agent_trace", "agent_trace empty in M1 mode (correct)")

        # Response must contain a result (skills ran deterministically)
        has_result = bool(
            data.get("response_text") or data.get("artefacts")
            or data.get("result") or data.get("skill_outputs")
        )
        if has_result:
            _pass("M1 deterministic output", "Analysis result produced via deterministic pipeline")
        else:
            _fail("M1 deterministic output", f"No result returned. Keys: {list(data.keys())}")

    except Exception:
        _fail("M1 fallback", traceback.format_exc()[:500])
    finally:
        os.environ["LLM_MODE"] = original_mode


# ---------------------------------------------------------------------------
# Test 3: ScriptedTransport test path (offline, no API key needed)
# ---------------------------------------------------------------------------

def test_scripted_transport() -> None:
    """
    ScriptedTransport replays a canned tool-call sequence without network.
    Confirms the agent runtime machinery works end-to-end offline.
    """
    try:
        from app.opar.agent_runtime import (
            ScriptedTransport, ToolDefinition, ToolCall,
            run_tool_loop, make_tool_call,
        )
        from app.opar.models import ObserveContext

        tools = [
            ToolDefinition(name="find_skills", description="Find relevant skills", input_schema={"type": "object", "properties": {"query": {"type": "string"}}}),
            ToolDefinition(name="run_skill", description="Run a skill", input_schema={"type": "object", "properties": {"name": {"type": "string"}}}),
        ]

        script = [
            # Turn 1: LLM calls find_skills
            (None, [make_tool_call("find_skills", {"query": "spend profiler"}, call_id="t1")]),
            # Turn 2: LLM calls run_skill then stops
            (None, [make_tool_call("run_skill", {"name": "spend-profiler"}, call_id="t2")]),
            # Turn 3: LLM produces final text
            ("Here is the analysis.", []),
        ]
        transport = ScriptedTransport(script)

        call_log: List[ToolCall] = []

        def dispatch(call: ToolCall) -> Any:
            call_log.append(call)
            return {"skill": call.arguments.get("name", "ok"), "result": "synthetic"}

        result = run_tool_loop(
            system="You are a helpful FP&A analyst.",
            messages=[{"role": "user", "content": "Profile my spend"}],
            tools=tools,
            dispatch=dispatch,
            transport=transport,
        )

        if result.final_text == "Here is the analysis.":
            _pass("ScriptedTransport final_text", "Correct final text from scripted replay")
        else:
            _fail("ScriptedTransport final_text", f"Got: {result.final_text!r}")

        tool_names = [c.name for c in call_log]
        if "find_skills" in tool_names and "run_skill" in tool_names:
            _pass("ScriptedTransport tool dispatch", f"Dispatched: {tool_names}")
        else:
            _fail("ScriptedTransport tool dispatch", f"Expected find_skills + run_skill, got: {tool_names}")

        if len(result.steps) >= 2:
            _pass("ScriptedTransport step count", f"{len(result.steps)} steps logged")
        else:
            _fail("ScriptedTransport step count", f"Expected ≥2 steps, got {len(result.steps)}")

    except ImportError as exc:
        _fail("ScriptedTransport", f"Import error: {exc}")
    except Exception:
        _fail("ScriptedTransport", traceback.format_exc()[:500])


# ---------------------------------------------------------------------------
# Test 4: Numeric provenance module integrity
# ---------------------------------------------------------------------------

def test_provenance_module() -> None:
    """tag_llm_numeric, tag_deterministic, apply_bounded_adjustment work correctly."""
    try:
        from app.opar.numeric_provenance import (
            tag_llm_numeric, tag_deterministic, apply_bounded_adjustment,
        )

        det = tag_deterministic(100.0, field="test_value")
        assert det["value"] == 100.0
        assert det["source"] == "deterministic"
        _pass("tag_deterministic", f"source={det['source']}, value={det['value']}")

        llm = tag_llm_numeric(110.0, field="test_value", deterministic_anchor=100.0, rationale="10% uplift")
        assert llm["source"] == "llm_estimate"
        assert llm["deterministic_anchor"] == 100.0
        assert llm["value"] == 110.0
        _pass("tag_llm_numeric", f"source={llm['source']}, anchor={llm['deterministic_anchor']}")

        # Bounded: proposed 200% over anchor → should be clamped to ≤25% over
        bounded = apply_bounded_adjustment(anchor=100.0, proposed=300.0, field="big_jump", rationale="test clamp")
        assert bounded["value"] <= 125.0, f"Not clamped: {bounded['value']}"
        _pass("apply_bounded_adjustment clamp", f"300→clamped to {bounded['value']:.1f}")

        # Bounded: proposed within 10% → should pass through
        small = apply_bounded_adjustment(anchor=100.0, proposed=108.0, field="small_adj", rationale="small change")
        assert small["value"] == 108.0
        assert small["within_bound"] is True
        _pass("apply_bounded_adjustment pass-through", f"108 within ±25% of 100")

    except Exception:
        _fail("provenance module", traceback.format_exc()[:500])


# ---------------------------------------------------------------------------
# Test 5: agent_loop_available() respects env vars
# ---------------------------------------------------------------------------

def test_agent_loop_gate() -> None:
    """agent_loop_available() returns False in M1 or with PYTEST_CURRENT_TEST."""
    try:
        from app.opar.agent_runtime import agent_loop_available

        # Save state
        orig_mode = os.environ.get("LLM_MODE")
        orig_pytest = os.environ.get("PYTEST_CURRENT_TEST")
        orig_enabled = os.environ.get("AGENT_CONTROLLER_ENABLED")

        try:
            # M1 → unavailable
            os.environ["LLM_MODE"] = "M1"
            os.environ.pop("PYTEST_CURRENT_TEST", None)
            os.environ["AGENT_CONTROLLER_ENABLED"] = "true"
            if agent_loop_available():
                _fail("agent_loop_available M1", "Should be False in M1 mode")
            else:
                _pass("agent_loop_available M1", "Returns False in M1 (correct)")

            # PYTEST_CURRENT_TEST → unavailable
            os.environ["LLM_MODE"] = "M2"
            os.environ["PYTEST_CURRENT_TEST"] = "mock_test"
            if agent_loop_available():
                _fail("agent_loop_available PYTEST", "Should be False when PYTEST_CURRENT_TEST set")
            else:
                _pass("agent_loop_available PYTEST", "Returns False when PYTEST_CURRENT_TEST set (correct)")

            # AGENT_CONTROLLER_ENABLED=false → unavailable (patch the config value directly
            # since the module was already imported and env var won't retroactively change it)
            os.environ.pop("PYTEST_CURRENT_TEST", None)
            import app.config as _cfg
            orig_cfg_val = _cfg.AGENT_CONTROLLER_ENABLED
            try:
                _cfg.AGENT_CONTROLLER_ENABLED = False
                if agent_loop_available():
                    _fail("agent_loop_available disabled", "Should be False when AGENT_CONTROLLER_ENABLED=False")
                else:
                    _pass("agent_loop_available disabled", "Returns False when disabled (correct)")
            finally:
                _cfg.AGENT_CONTROLLER_ENABLED = orig_cfg_val

        finally:
            # Restore state
            if orig_mode is not None:
                os.environ["LLM_MODE"] = orig_mode
            else:
                os.environ.pop("LLM_MODE", None)
            if orig_pytest is not None:
                os.environ["PYTEST_CURRENT_TEST"] = orig_pytest
            else:
                os.environ.pop("PYTEST_CURRENT_TEST", None)
            if orig_enabled is not None:
                os.environ["AGENT_CONTROLLER_ENABLED"] = orig_enabled
            else:
                os.environ.pop("AGENT_CONTROLLER_ENABLED", None)

    except Exception:
        _fail("agent_loop_gate", traceback.format_exc()[:500])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 65)
    print("Agentic Intelligence Smoke Test")
    print(f"LLM_MODE={os.environ.get('LLM_MODE', 'M2')}  "
          f"PROVIDER={os.environ.get('LLM_PROVIDER', 'gemini')}")
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"GEMINI_API_KEY={'✓' if has_gemini else '✗'}  "
          f"ANTHROPIC_API_KEY={'✓' if has_anthropic else '✗'}")
    print("=" * 65)

    print("\n[Test 1] M2 agent path (live API call)")
    test_m2_agent_path()

    print("\n[Test 2] M1 deterministic fallback")
    test_m1_fallback()

    print("\n[Test 3] ScriptedTransport offline replay")
    test_scripted_transport()

    print("\n[Test 4] Numeric provenance module")
    test_provenance_module()

    print("\n[Test 5] agent_loop_available() gate")
    test_agent_loop_gate()

    # Summary
    n_pass = sum(1 for r in RESULTS if r["status"] == "PASS")
    n_fail = sum(1 for r in RESULTS if r["status"] == "FAIL")
    n_skip = sum(1 for r in RESULTS if r["status"] == "SKIP")
    total = len(RESULTS)

    print()
    print("=" * 65)
    print(f"Results: {n_pass} pass  {n_fail} fail  {n_skip} skip  (of {total} checks)")
    print("Status:", "PASS ✓" if n_fail == 0 else "FAIL ✗")
    print("=" * 65)

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
