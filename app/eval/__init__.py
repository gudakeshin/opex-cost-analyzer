"""Evaluation framework for the OpEx Intelligence Platform.

Three-layer evaluation:
  Layer 1 — Skill-level golden dataset unit tests (app/eval/golden.py)
  Layer 2 — Pipeline-level trace grounding     (app/eval/trace.py + judge.py)
  Layer 3 — Relevance / counterfactual testing (app/eval/counterfactual.py)

Expert review bundle generation: app/eval/review.py
"""
