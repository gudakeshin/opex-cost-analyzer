#!/usr/bin/env python3
"""Presentation structure eval — scores hybrid block+narrative responses.

Uses golden fixtures under tests/eval/golden/presentation/. Exit 0 when all
scenarios pass threshold (default 7.0/10).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
GOLDEN_DIR = ROOT / "tests" / "eval" / "golden" / "presentation"
THRESHOLD = 7.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from app.opar.models import ObserveContext
    from app.opar.presentation import assemble_assistant_payload, presentation_structure_score

    results = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        fx = json.loads(path.read_text())
        ctx = ObserveContext(**fx["observe_context"])
        payload = assemble_assistant_payload(None, fx["validated"], ctx)
        score, evidence = presentation_structure_score(payload)
        category_blocks = [b for b in payload.blocks if b.kind == "category_insight"]
        min_expected = int(fx.get("expected_min_category_blocks", 1))
        passed = score >= THRESHOLD and len(category_blocks) >= min_expected
        row = {
            "fixture": path.name,
            "score": round(score, 2),
            "passed": passed,
            "category_insight_count": len(category_blocks),
            "evidence": evidence,
        }
        results.append(row)

    if args.json_only:
        print(json.dumps(results, indent=2))
    else:
        for row in results:
            status = "PASS" if row["passed"] else "FAIL"
            print(f"{status} {row['fixture']}: {row['score']}/10 ({row['category_insight_count']} category blocks)")
        overall = sum(r["score"] for r in results) / len(results) if results else 0.0
        print(f"\nOverall: {overall:.2f}/10")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
