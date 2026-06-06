"""Session-scoped execution context for agent tools."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.models import NormalizedSpendLine
from app.opar.models import ObserveContext


@dataclass
class ToolSessionContext:
    """Mutable session state shared across tool calls within one agent turn."""

    ctx: ObserveContext
    lines: List[NormalizedSpendLine] = field(default_factory=list)
    docs_text: List[str] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)
    skill_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)
    degradation_reasons: Dict[str, str] = field(default_factory=dict)
    opportunity_assessment: Dict[str, Any] | None = None
    agent_trace: List[Dict[str, Any]] = field(default_factory=list)
    skills_run: List[str] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return self.ctx.session_id

    @property
    def engagement_id(self) -> str:
        return self.ctx.engagement_id or self.ctx.session_id

    @property
    def user_message(self) -> str:
        return self.ctx.user_message

    def load_session_data(self) -> None:
        if self.lines or self.manifest:
            return
        from app.opar.act import _load_session_data

        self.lines, self.docs_text, self.manifest = _load_session_data(self.session_id)

    def invoke_skill(self, skill_name: str) -> Dict[str, Any]:
        """Run one skill with deps auto-resolved; returns compact output summary."""
        from app.opar.plan import resolve_skill_dependencies
        from app.skills.dispatch import registered_skills

        if skill_name not in registered_skills():
            raise ValueError(f"Unknown skill: {skill_name}")

        self.load_session_data()
        for dep in resolve_skill_dependencies([skill_name]):
            if dep in self.skill_outputs or dep in self.errors:
                continue
            self._run_one(dep)

        # Safety: run the skill itself when it isn't in _DEP_MAP (dep list returns [])
        if skill_name not in self.skill_outputs and skill_name not in self.errors:
            self._run_one(skill_name)

        if skill_name in self.skill_outputs:
            return self._summarize_skill_output(skill_name, self.skill_outputs[skill_name])
        if skill_name in self.errors:
            raise RuntimeError(self.errors[skill_name])
        return {}

    def _run_one(self, skill_name: str) -> None:
        from app.skills.dispatch import SkillContext, invoke_skill

        ctx = SkillContext(
            lines=self.lines,
            docs_text=self.docs_text,
            manifest=self.manifest,
            prior_results=self.skill_outputs,
            user_message=self.user_message,
            headcount=self.ctx.headcount,
            wacc=float(self.manifest.get("wacc") or 0.10),
            effective_tax_rate=float(self.manifest.get("effective_tax_rate") or 0.0),
            reporting_currency=str(
                self.manifest.get("currency") or self.manifest.get("reporting_currency") or "USD"
            ),
            entity_tree=self.manifest.get("entity_tree"),
            segment_revenue=self.manifest.get("segment_revenue"),
            sector_weights=self.manifest.get("sector_weights"),
        )
        try:
            output, degraded = invoke_skill(skill_name, ctx)
            self.skill_outputs[skill_name] = output
            if degraded:
                self.degradation_reasons[skill_name] = degraded
            if skill_name not in self.skills_run:
                self.skills_run.append(skill_name)
        except Exception as exc:
            self.errors[skill_name] = str(exc)[:500]

    @staticmethod
    def _summarize_skill_output(skill_name: str, output: Dict[str, Any]) -> Dict[str, Any]:
        """Return a compact JSON-friendly view for the LLM."""
        if skill_name == "spend-profiler":
            cats = output.get("category_profile") or []
            return {
                "skill": skill_name,
                "total_spend": output.get("total_spend"),
                "category_count": len(cats),
                "top_categories": cats[:8],
            }
        if skill_name == "peer-benchmarker":
            gaps = output.get("benchmark_gaps") or output.get("gaps") or []
            return {"skill": skill_name, "gap_count": len(gaps), "gaps": gaps[:10]}
        if skill_name == "savings-modeler":
            opps = output.get("opportunities") or output.get("initiatives") or []
            return {"skill": skill_name, "opportunity_count": len(opps), "opportunities": opps[:8]}
        if skill_name == "evidence-gatherer":
            items = output.get("evidence_items") or output.get("items") or []
            return {"skill": skill_name, "evidence_count": len(items), "items": items[:6]}
        if skill_name == "sme-critique":
            return {
                "skill": skill_name,
                "maturity_score": output.get("maturity_score"),
                "initiatives": (output.get("initiatives") or [])[:6],
            }
        # Generic truncation
        text = str(output)
        if len(text) > 6000:
            return {"skill": skill_name, "summary": text[:6000], "_truncated": True}
        return {"skill": skill_name, **output}

    def to_act_result(self):
        from app.opar.models import ActResult

        return ActResult(
            skill_outputs=dict(self.skill_outputs),
            errors=dict(self.errors),
            degradation_reasons=dict(self.degradation_reasons),
            normalized_spend=list(self.lines),
        )

    def to_execution_plan(self):
        from app.opar.models import ExecutionPlan, SkillTask
        from app.opar.plan import get_skill_dep_map

        dep_map = get_skill_dep_map()
        tasks: List[SkillTask] = []
        for name in self.skills_run:
            if name not in dep_map:
                tasks.append(SkillTask(skill_name=name, inputs={}, depends_on=[], parallel_group=0))
                continue
            group, deps, tokens = dep_map[name]
            tasks.append(
                SkillTask(
                    skill_name=name,
                    inputs={},
                    depends_on=[d for d in deps if d in self.skills_run],
                    parallel_group=group,
                    estimated_tokens=tokens,
                )
            )
        return ExecutionPlan(
            tasks=tasks,
            total_skills=len(tasks),
            parallel_groups=max((t.parallel_group for t in tasks), default=0) + 1 if tasks else 0,
            user_summary="Agent-selected analysis path",
            estimated_duration="agent",
            requires_approval=False,
        )
