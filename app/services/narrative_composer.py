"""Deterministic CXO-grade narrative from skill outputs (no LLM required)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.opar.models import (
    AdvisoryActionItem,
    AdvisoryBusinessLever,
    AdvisoryCitation,
    AdvisorySections,
    ObserveContext,
)
from app.opar.reflect_advisory import advisory_quality_ok
from app.utils.inr_format import format_money


def _fmt(amount: float, currency: str) -> str:
    return format_money(float(amount or 0.0), currency)


def _root_causes_by_category(outputs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in outputs.get("root-cause-analyzer", {}).get("root_cause_findings", []) or []:
        if isinstance(row, dict):
            cid = str(row.get("category_id") or "")
            if cid:
                out[cid] = row
    return out


def _benchmark_rows(outputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    peer = outputs.get("peer-benchmarker", {}) or {}
    rows = peer.get("comparisons") or peer.get("benchmark_gaps") or []
    return [r for r in rows if isinstance(r, dict)]


def _top_benchmark_gaps(outputs: Dict[str, Any], limit: int = 2) -> List[Dict[str, Any]]:
    rows = _benchmark_rows(outputs)
    rows.sort(
        key=lambda r: float(r.get("estimated_saving_amount") or r.get("benchmark_gap_pct") or 0),
        reverse=True,
    )
    return rows[:limit]


def _benchmark_gap_sentence(row: Dict[str, Any], currency: str) -> str:
    cat = row.get("category_name") or row.get("category_id") or "Category"
    band = row.get("percentile_band") or "above peer"
    actual = row.get("actual_pct_of_revenue")
    p50 = row.get("benchmark_p50_pct") or row.get("benchmark_target_pct")
    gap_amt = float(row.get("estimated_saving_amount") or 0.0)
    pct_bits: List[str] = []
    if actual is not None and p50 is not None:
        pct_bits.append(f"actual {float(actual):.1f}% vs peer median {float(p50):.1f}% of revenue")
    if gap_amt > 0:
        pct_bits.append(f"{_fmt(gap_amt, currency)} gap")
    detail = " — ".join(pct_bits) if pct_bits else "material peer variance"
    return f"{cat} at {band} ({detail})"


def _portfolio_ebitda_bps(outputs: Dict[str, Any]) -> float | None:
    summary = outputs.get("savings-modeler", {}).get("summary", {}) or {}
    bps = summary.get("portfolio_ebitda_impact_bps")
    if bps is not None:
        return float(bps)
    total = 0.0
    count = 0
    for init in outputs.get("savings-modeler", {}).get("initiatives", []) or []:
        eb = (init.get("ebitda_impact") or {}).get("ebitda_bps")
        if eb is not None:
            total += float(eb)
            count += 1
    return total if count else None


def _downside_floor(outputs: Dict[str, Any], currency: str) -> str | None:
    sm = outputs.get("scenario-modeler", {}) or {}
    floor = sm.get("downside_floor")
    if floor is None:
        return None
    pct = sm.get("downside_floor_pct_of_base")
    text = f"sensitivity downside floor {_fmt(float(floor), currency)}"
    if pct is not None:
        # the scenario-modeler reports percentage points (70.0 = 70%), not a fraction
        text += f" ({float(pct):.0f}% of base case)"
    return text


def _executive_takeaway(
    outputs: Dict[str, Any],
    *,
    company_name: str,
    currency: str,
) -> str:
    bridge = outputs.get("value-bridge-calculator", {}) or {}
    conf = bridge.get("confidence_bands", {}) or {}
    low = float(conf.get("low", 0) or 0)
    mid = float(conf.get("mid", 0) or 0)
    high = float(conf.get("high", 0) or 0)

    sentences: List[str] = [
        (
            f"{company_name} has a modeled OpEx savings opportunity of {_fmt(mid, currency)} "
            f"(mid-case), with a confidence band of {_fmt(low, currency)} to {_fmt(high, currency)}."
        )
    ]

    gaps = _top_benchmark_gaps(outputs, limit=2)
    if gaps:
        gap_text = "; ".join(_benchmark_gap_sentence(g, currency) for g in gaps)
        sentences.append(f"The largest benchmark gaps are {gap_text}.")

    bps = _portfolio_ebitda_bps(outputs)
    if bps is not None:
        sentences.append(f"Portfolio realization lifts EBITDA by approximately {bps:.0f} bps at mid-case.")

    floor_line = _downside_floor(outputs, currency)
    if floor_line:
        sentences.append(f"Under conservative execution assumptions, {floor_line}.")

    initiatives = outputs.get("savings-modeler", {}).get("initiatives", []) or []
    if initiatives:
        sentences.append(
            f"{len(initiatives)} initiatives are modeled with traceable root-cause linkage and payback horizons."
        )

    return " ".join(sentences)


def _spend_by_category(outputs: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in outputs.get("spend-profiler", {}).get("category_profile", []) or []:
        if isinstance(row, dict):
            cid = str(row.get("category_id") or "")
            if cid:
                out[cid] = row
    return out


def _lever_so_what(
    init: Dict[str, Any],
    bench: Dict[str, Any] | None,
    spend_cat: Dict[str, Any] | None,
    currency: str,
) -> str:
    """Per-lever implication line from data at hand — never fabricated."""
    parts: List[str] = []
    eb = (init.get("ebitda_impact") or {}).get("ebitda_bps")
    if eb is not None:
        bps = float(eb)
        if bps != 0:
            parts.append(f"~{bps:.0f} bps EBITDA uplift at mid-case realization")
    if bench:
        gap = float(bench.get("estimated_saving_amount") or 0)
        if gap > 0:
            parts.append(f"closing peer gap unlocks {_fmt(gap, currency)}")
    if spend_cat and spend_cat.get("concentration_flag") == "high":
        suppliers = spend_cat.get("top_suppliers") or []
        if suppliers and isinstance(suppliers[0], dict):
            share = float(suppliers[0].get("share_of_category") or 0)
            if share >= 0.4:
                name = suppliers[0].get("supplier") or "top supplier"
                parts.append(f"{name} holds {share:.0%} — negotiation leverage is high")
    payback = init.get("payback_months")
    if payback is not None:
        parts.append(f"{int(payback)}-month payback if executed")
    return "; ".join(parts[:3])


def _sme_qualification_narrative(outputs: Dict[str, Any], currency: str) -> str:
    """Compose SME critique narrative from sme-critique skill output."""
    sme = outputs.get("sme-critique", {}) or {}
    summary = sme.get("critique_summary") or {}
    critiques = [c for c in (sme.get("initiative_critiques") or []) if isinstance(c, dict)]
    if not summary and not critiques:
        return ""

    parts: List[str] = []
    total = int(summary.get("total_initiatives") or len(critiques))
    if total > 0:
        ready = int(summary.get("ready_count") or 0)
        probe = int(summary.get("probe_count") or 0)
        insufficient = int(summary.get("insufficient_count") or 0)
        savings_ready = float(summary.get("savings_ready") or 0)
        savings_probe = float(summary.get("savings_probe") or 0)
        savings_insufficient = float(summary.get("savings_insufficient") or 0)
        parts.append(
            f"Of {total} modeled initiatives, {ready} are ready to proceed "
            f"({_fmt(savings_ready, currency)}), {probe} need probe validation "
            f"({_fmt(savings_probe, currency)}), and {insufficient} have insufficient evidence "
            f"({_fmt(savings_insufficient, currency)})."
        )

    weak = sorted(
        critiques,
        key=lambda c: (int(c.get("maturity_score") or 0), float(c.get("modelled_saving_3yr") or 0)),
    )
    named = 0
    for c in weak:
        if named >= 3:
            break
        verdict = str(c.get("sme_verdict") or "")
        maturity = str(c.get("evidence_maturity") or "hypothesis")
        if verdict == "proceed" and maturity in ("validated", "supported"):
            continue
        cat = c.get("category_name") or c.get("category_id") or "Category"
        lever = c.get("lever_name") or c.get("lever") or "initiative"
        saving = float(c.get("modelled_saving_3yr") or 0)
        gaps = c.get("gaps") or []
        gap_text = str(gaps[0]) if gaps else "limited supporting data"
        parts.append(
            f"**{cat} / {lever}** ({_fmt(saving, currency)}, {maturity} evidence): {gap_text}."
        )
        named += 1

    dc = [c for c in critiques if c.get("double_count_risk")]
    if dc:
        labels = ", ".join(
            f"{c.get('category_name', c.get('category_id'))}/{c.get('lever_name', c.get('lever'))}"
            for c in dc[:2]
        )
        parts.append(
            f"Double-count risk flagged for {labels} — validate savings stacking before committing."
        )

    top_probes = sme.get("top_probes") or sme.get("portfolio_probes") or []
    for probe in top_probes:
        if not isinstance(probe, dict):
            continue
        question = str(probe.get("question") or probe.get("probe_question") or "").strip()
        if not question:
            continue
        data_req = str(probe.get("data_to_request") or probe.get("why_critical") or "").strip()
        line = f"Priority probe: {question}"
        if data_req:
            line += f" Data to request: {data_req}."
        parts.append(line)
        break

    return " ".join(parts)


def _lever_evidence(
    init: Dict[str, Any],
    rc_row: Dict[str, Any] | None,
    bench_row: Dict[str, Any] | None,
    currency: str,
) -> List[str]:
    evidence: List[str] = []
    lever_name = init.get("lever_name") or init.get("lever") or "lever"
    cat = init.get("category_name") or init.get("category_id") or "category"
    rr = float(init.get("annualized_run_rate_savings") or 0.0)
    if rr > 0:
        evidence.append(f"[savings-modeler] {lever_name} annualized run-rate {_fmt(rr, currency)} in {cat}.")
    payback = init.get("payback_months")
    if payback is not None:
        evidence.append(f"[savings-modeler] Payback {payback} months at modeled CTA.")
    if bench_row:
        evidence.append(
            f"[peer-benchmarker] {cat}: {bench_row.get('percentile_band', 'above peer')} — "
            f"{bench_row.get('actual_pct_of_revenue', '?')}% vs P50 {bench_row.get('benchmark_p50_pct', '?')}% of revenue."
        )
    if rc_row:
        causes = rc_row.get("root_causes") or []
        if causes and isinstance(causes[0], dict):
            evidence.append(f"[root-cause-analyzer] {causes[0].get('diagnosis', 'Root cause identified')}.")
    signals = init.get("diagnostic_signals") or []
    for sig in signals[:1]:
        if isinstance(sig, dict) and sig.get("signal"):
            evidence.append(f"[savings-modeler] Signal: {sig['signal']}.")
    while len(evidence) < 2:
        root = init.get("root_cause") or "benchmark-driven addressable spend"
        evidence.append(f"[value-bridge-calculator] Initiative targets {root} in {cat}.")
        if len(evidence) >= 2:
            break
    return evidence[:4]


def _business_levers(
    outputs: Dict[str, Any],
    currency: str,
) -> List[AdvisoryBusinessLever]:
    initiatives = outputs.get("savings-modeler", {}).get("initiatives", []) or []
    rc_by_cat = _root_causes_by_category(outputs)
    bench_by_cat = {str(r.get("category_id")): r for r in _benchmark_rows(outputs) if r.get("category_id")}
    spend_by_cat = _spend_by_category(outputs)

    levers: List[AdvisoryBusinessLever] = []
    for init in initiatives:
        if not isinstance(init, dict):
            continue
        cid = str(init.get("category_id") or "")
        rc = rc_by_cat.get(cid)
        bench = bench_by_cat.get(cid)
        lever_name = str(init.get("lever_name") or init.get("lever") or "Initiative")
        cat = str(init.get("category_name") or cid or "category")

        what_changes_parts: List[str] = []
        if rc:
            for cause in (rc.get("root_causes") or [])[:1]:
                if isinstance(cause, dict):
                    approach = cause.get("implementation_approach") or cause.get("recommended_lever")
                    if approach:
                        what_changes_parts.append(str(approach))
        playbook = init.get("execution_playbook") or []
        if playbook and isinstance(playbook[0], dict):
            what_changes_parts.append(str(playbook[0].get("step") or playbook[0].get("action") or playbook[0]))
        elif playbook:
            what_changes_parts.append(str(playbook[0]))
        if not what_changes_parts:
            what_changes_parts.append(
                f"Reset commercial terms and operating controls for {lever_name} in {cat}."
            )
        what_changes = " ".join(what_changes_parts)[:280]

        why_parts: List[str] = []
        root = init.get("root_cause") or (rc.get("root_causes", [{}])[0].get("diagnosis") if rc else None)
        if root:
            why_parts.append(f"Addresses {root}.")
        if bench:
            why_parts.append(
                f"Peer gap at {bench.get('percentile_band', 'elevated percentile')} "
                f"({bench.get('actual_pct_of_revenue')}% vs median {bench.get('benchmark_p50_pct')}%)."
            )
        conf = init.get("confidence") or "medium"
        why_parts.append(f"Modeled confidence: {conf}.")
        why_it_works = " ".join(why_parts)[:280]

        levers.append(
            AdvisoryBusinessLever(
                lever_name=lever_name,
                what_changes=what_changes,
                why_it_works=why_it_works,
                evidence=_lever_evidence(init, rc, bench, currency),
                so_what=_lever_so_what(init, bench, spend_by_cat.get(cid), currency),
            )
        )
    return levers


def _quick_wins(outputs: Dict[str, Any], currency: str) -> List[str]:
    wins: List[str] = []
    for init in sorted(
        outputs.get("savings-modeler", {}).get("initiatives", []) or [],
        key=lambda i: int(i.get("payback_months") or 99),
    ):
        if not isinstance(init, dict):
            continue
        payback = int(init.get("payback_months") or 99)
        if payback > 9:
            continue
        name = init.get("lever_name") or init.get("lever")
        cat = init.get("category_name") or init.get("category_id")
        rr = float(init.get("annualized_run_rate_savings") or 0.0)
        wins.append(
            f"[savings-modeler] {name} in {cat}: {_fmt(rr, currency)} run-rate, payback {payback} months."
        )
        if len(wins) >= 5:
            break

    for row in _top_benchmark_gaps(outputs, limit=2):
        gap = float(row.get("estimated_saving_amount") or 0.0)
        if gap > 0:
            wins.append(
                f"[peer-benchmarker] Close {row.get('category_name', row.get('category_id'))} gap "
                f"({_fmt(gap, currency)} vs peer median)."
            )

    for c in outputs.get("spend-profiler", {}).get("category_profile", []) or []:
        if not isinstance(c, dict):
            continue
        if c.get("concentration_flag") == "high" and c.get("top_suppliers"):
            sup = c["top_suppliers"][0]
            wins.append(
                f"[spend-profiler] Renegotiate {sup.get('supplier')} "
                f"({float(sup.get('share_of_category', 0) or 0):.0%} of {c.get('category_name')})."
            )
            break

    return wins[:6]


def _executive_callouts(outputs: Dict[str, Any], currency: str) -> List[str]:
    callouts: List[str] = []
    conf = outputs.get("value-bridge-calculator", {}).get("confidence_bands", {}) or {}
    mid = float(conf.get("mid", 0) or 0)
    if mid > 0:
        callouts.append(f"[value-bridge-calculator] Mid-case portfolio savings {_fmt(mid, currency)}.")
    for row in _top_benchmark_gaps(outputs, limit=2):
        callouts.append(f"[peer-benchmarker] {_benchmark_gap_sentence(row, currency)}.")
    bps = _portfolio_ebitda_bps(outputs)
    if bps is not None:
        callouts.append(f"[savings-modeler] Portfolio EBITDA uplift ~{bps:.0f} bps at realization.")
    sm = outputs.get("scenario-modeler", {}) or {}
    if sm.get("p10_savings") is not None and sm.get("p90_savings") is not None:
        callouts.append(
            f"[scenario-modeler] P10–P90 savings band "
            f"{_fmt(float(sm['p10_savings']), currency)} – {_fmt(float(sm['p90_savings']), currency)}."
        )
    return callouts[:5]


def _category_section_for_row(
    cat_name: str,
    init: Dict[str, Any] | None,
    bench: Dict[str, Any] | None,
    rc: Dict[str, Any] | None,
    currency: str,
) -> str:
    lines = [f"## {cat_name}", ""]
    why: List[str] = []
    if bench:
        why.append(
            f"Spend runs at {bench.get('actual_pct_of_revenue')}% of revenue versus peer median "
            f"{bench.get('benchmark_p50_pct')}% ({bench.get('percentile_band', 'elevated')} band)."
        )
    if rc:
        for cause in (rc.get("root_causes") or [])[:2]:
            if isinstance(cause, dict) and cause.get("diagnosis"):
                why.append(str(cause["diagnosis"]))
    if init and init.get("root_cause"):
        why.append(str(init["root_cause"]))
    if not why:
        why.append("Uploaded spend and benchmark data show addressable variance above peer norms.")
    lines.append("### Why the gap exists")
    lines.append("")
    lines.append(" ".join(why))
    lines.append("")
    lines.append("### What should change")
    lines.append("")
    change_bits: List[str] = []
    if init:
        lever = init.get("lever_name") or init.get("lever")
        if lever:
            change_bits.append(f"Execute {lever} with accountable owner sponsorship.")
        for step in (init.get("execution_playbook") or [])[:2]:
            if isinstance(step, dict):
                change_bits.append(str(step.get("step") or step.get("action") or step))
            else:
                change_bits.append(str(step))
    if rc:
        for cause in (rc.get("root_causes") or [])[:1]:
            if isinstance(cause, dict) and cause.get("implementation_approach"):
                change_bits.append(str(cause["implementation_approach"]))
    if not change_bits:
        change_bits.append("Tighten demand, commercial, and governance controls on the top vendors in-category.")
    lines.append(" ".join(change_bits))
    lines.append("")
    lines.append("### Leadership decision")
    lines.append("")
    rr = float((init or {}).get("annualized_run_rate_savings") or 0.0)
    decision = (
        "CFO and category owner must commit a 90-day mandate"
        + (f" targeting {_fmt(rr, currency)} run-rate" if rr > 0 else "")
        + f" in {cat_name}, with monthly realization tracking."
    )
    lines.append(decision)
    return "\n".join(lines)


def _category_focus_section(
    outputs: Dict[str, Any],
    currency: str,
    *,
    focus_category_id: str | None = None,
) -> str:
    initiatives = outputs.get("savings-modeler", {}).get("initiatives", []) or []
    rc_by_cat = _root_causes_by_category(outputs)
    bench_by_cat = {str(r.get("category_id")): r for r in _benchmark_rows(outputs) if r.get("category_id")}

    if focus_category_id and focus_category_id in bench_by_cat:
        cat_ids = [focus_category_id]
    else:
        ordered = _top_benchmark_gaps(outputs, limit=4)
        cat_ids = [str(r.get("category_id")) for r in ordered if r.get("category_id")]
        if not cat_ids:
            cat_ids = [str(i.get("category_id")) for i in initiatives if i.get("category_id")][:3]

    sections: List[str] = []
    for cid in cat_ids:
        init = next((i for i in initiatives if str(i.get("category_id")) == cid), None)
        cat_name = (
            (init or {}).get("category_name")
            or (bench_by_cat.get(cid) or {}).get("category_name")
            or cid
        )
        sections.append(
            _category_section_for_row(
                str(cat_name),
                init if isinstance(init, dict) else None,
                bench_by_cat.get(cid),
                rc_by_cat.get(cid),
                currency,
            )
        )
    return "\n\n".join(sections)


def _priority_actions(
    outputs: Dict[str, Any],
    currency: str,
) -> List[AdvisoryActionItem]:
    initiatives = [
        i for i in outputs.get("savings-modeler", {}).get("initiatives", []) or [] if isinstance(i, dict)
    ]
    actions: List[AdvisoryActionItem] = []
    quick = sorted(initiatives, key=lambda i: int(i.get("payback_months") or 99))[:2]
    for init in quick:
        name = init.get("lever_name") or init.get("lever")
        cat = init.get("category_name") or init.get("category_id")
        owner = init.get("owner_role") or "category owner"
        actions.append(
            AdvisoryActionItem(
                timeline="30",
                action=f"Mobilize {name} in {cat} — confirm {owner} and baseline spend.",
                expected_impact=init.get("phasing_narrative")
                or f"Quick-win path, payback {init.get('payback_months', '?')} months",
            )
        )
    structural = [i for i in initiatives if i not in quick][:2]
    for init in structural:
        name = init.get("lever_name") or init.get("lever")
        cat = init.get("category_name") or init.get("category_id")
        rr = float(init.get("annualized_run_rate_savings") or 0.0)
        actions.append(
            AdvisoryActionItem(
                timeline="60",
                action=f"Negotiate and execute {name} in {cat}.",
                expected_impact=f"~{_fmt(rr, currency)} run-rate at steady state",
            )
        )
    actions.append(
        AdvisoryActionItem(
            timeline="90",
            action="Institutionalize monthly pipeline governance and bounce-back controls across committed initiatives.",
            expected_impact="Sustained realization vs scenario downside floor",
        )
    )
    return actions


def build_citations(outputs: Dict[str, Any], currency: str = "INR") -> List[AdvisoryCitation]:
    """Compute claim-to-data citations from skill outputs (never hallucinated)."""
    citations: List[AdvisoryCitation] = []
    peer = outputs.get("peer-benchmarker", {}) or {}
    dataset = peer.get("benchmark_dataset") or peer.get("benchmark_metadata") or {}
    ds_name = str(dataset.get("source") or dataset.get("dataset_name") or peer.get("industry") or "")
    vintage = str(dataset.get("vintage_date") or dataset.get("vintage") or "")

    for row in _benchmark_rows(outputs):
        citations.append(
            AdvisoryCitation(
                source_skill="peer-benchmarker",
                metric=f"{row.get('category_name', row.get('category_id'))} vs peer",
                value=(
                    f"{row.get('actual_pct_of_revenue')}% actual vs "
                    f"{row.get('benchmark_p50_pct')}% P50 ({row.get('percentile_band', 'gap')})"
                ),
                row_count=1,
                dataset=ds_name,
                vintage=vintage,
                sample_n=int(row.get("benchmark_sample_n") or dataset.get("sample_n") or 0),
            )
        )

    for row in outputs.get("root-cause-analyzer", {}).get("root_cause_findings", []) or []:
        if not isinstance(row, dict):
            continue
        n_causes = len(row.get("root_causes") or [])
        citations.append(
            AdvisoryCitation(
                source_skill="root-cause-analyzer",
                metric=f"{row.get('category_name', row.get('category_id'))} root causes",
                value=f"{n_causes} diagnosed drivers",
                row_count=n_causes,
            )
        )

    n_init = len(outputs.get("savings-modeler", {}).get("initiatives", []) or [])
    if n_init:
        summary = outputs.get("savings-modeler", {}).get("summary", {}) or {}
        citations.append(
            AdvisoryCitation(
                source_skill="savings-modeler",
                metric="portfolio initiatives",
                value=f"{n_init} initiatives; run-rate {_fmt(float(summary.get('total_run_rate_savings') or 0), currency)}",
                row_count=n_init,
            )
        )

    bridge = outputs.get("value-bridge-calculator", {}) or {}
    conf = bridge.get("confidence_bands", {}) or {}
    if conf:
        citations.append(
            AdvisoryCitation(
                source_skill="value-bridge-calculator",
                metric="confidence bands",
                value=f"low {_fmt(float(conf.get('low', 0)), currency)} / mid {_fmt(float(conf.get('mid', 0)), currency)} / high {_fmt(float(conf.get('high', 0)), currency)}",
                row_count=len(bridge.get("value_matrix", []) or []),
            )
        )

    n_cats = len(outputs.get("spend-profiler", {}).get("category_profile", []) or [])
    total = float(outputs.get("spend-profiler", {}).get("total_spend", 0) or 0)
    if n_cats or total:
        citations.append(
            AdvisoryCitation(
                source_skill="spend-profiler",
                metric="spend base",
                value=f"{_fmt(total, currency)} across {n_cats} categories",
                row_count=n_cats,
            )
        )
    return citations


def attach_citations(advisory: AdvisorySections, outputs: Dict[str, Any], currency: str = "INR") -> AdvisorySections:
    computed = build_citations(outputs, currency=currency)
    if not computed:
        return advisory
    merged = list(advisory.citations or [])
    seen = {(c.source_skill, c.metric) for c in merged}
    for c in computed:
        key = (c.source_skill, c.metric)
        if key not in seen:
            merged.append(c)
            seen.add(key)
    return advisory.model_copy(update={"citations": merged})


def compose_deterministic_advisory(
    outputs: Dict[str, Any],
    *,
    company_name: str = "Client",
    currency: str = "INR",
    category_focused: bool = False,
    focus_category_id: str | None = None,
    sparse_note: bool = False,
) -> AdvisorySections:
    """Render CXO-grade advisory sections purely from skill outputs."""
    takeaway = _executive_takeaway(outputs, company_name=company_name, currency=currency)
    levers = _business_levers(outputs, currency)
    quick = _quick_wins(outputs, currency)
    callouts = _executive_callouts(outputs, currency)
    focus = _category_focus_section(outputs, currency, focus_category_id=focus_category_id)
    actions = _priority_actions(outputs, currency)

    sme_note = _sme_qualification_narrative(outputs, currency)
    if not sme_note and (sparse_note or len(levers) < 3):
        sme_note = (
            "Deterministic narrative composed from available skill outputs; "
            "some portfolio sections are sparse — upload fuller spend or run additional skills for depth."
        )

    advisory = AdvisorySections(
        executive_takeaway=takeaway,
        category_focus_section=focus,
        quick_wins_from_data=quick,
        business_levers=levers,
        executive_callouts=callouts,
        priority_actions_30_60_90=actions,
        sme_qualification_narrative=sme_note,
    )
    return attach_citations(advisory, outputs, currency=currency)


def compose_from_context(
    ctx: ObserveContext | None,
    outputs: Dict[str, Any],
    manifest: Dict[str, Any] | None = None,
) -> AdvisorySections:
    """Convenience wrapper using session manifest + ObserveContext."""
    manifest = manifest or {}
    currency = str(manifest.get("currency") or manifest.get("reporting_currency") or "INR").upper()
    company = str(manifest.get("company_name") or "Client")
    focus_id = (ctx.explicit_category if ctx else None) or None
    from app.opar.reflect_focus import match_focus_category

    if ctx and not focus_id:
        row = match_focus_category(ctx, outputs)
        if row:
            focus_id = str(row.get("category_id") or "") or None
    explicit = (ctx.explicit_category if ctx else None) or ""
    sparse = not (
        outputs.get("savings-modeler", {}).get("initiatives")
        and outputs.get("peer-benchmarker", {}).get("comparisons")
    )
    advisory = compose_deterministic_advisory(
        outputs,
        company_name=company,
        currency=currency,
        category_focused=bool(ctx and (explicit or focus_id)),
        focus_category_id=focus_id,
        sparse_note=sparse,
    )
    if explicit and explicit not in (advisory.executive_takeaway or ""):
        advisory = advisory.model_copy(
            update={
                "executive_takeaway": (
                    f"{advisory.executive_takeaway} Focus category: {explicit}."
                ).strip()
            }
        )
    return advisory


def narrative_provenance_payload(mode: str, llm_skip_reason: str | None = None) -> Dict[str, Any]:
    return {"mode": mode, "llm_skip_reason": llm_skip_reason}


def provenance_banner_text(provenance: Dict[str, Any] | None) -> str | None:
    if not provenance or provenance.get("mode") != "deterministic":
        return None
    reason = str(provenance.get("llm_skip_reason") or "provider_unavailable").replace("_", " ")
    return f"Deterministic narrative — LLM unavailable: {reason}."


def quality_status(advisory: AdvisorySections, *, category_focused: bool = False) -> Tuple[bool, str]:
    ok = advisory_quality_ok(advisory, category_focused=category_focused)
    if ok:
        return True, "ok"
    if len(advisory.business_levers) >= 1 and len((advisory.executive_takeaway or "").strip()) >= 25:
        return False, "partial"
    return False, "sparse"
