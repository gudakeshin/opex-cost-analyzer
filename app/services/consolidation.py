"""Multi-Entity Consolidation Engine — Phase 2.

Rolls up spend across legal entities, eliminates intercompany transactions,
and produces a consolidated + entity-level view for Indian conglomerates.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.models import EntityTree, NormalizedSpendLine

logger = logging.getLogger("opex.consolidation")


# ---------------------------------------------------------------------------
# Data classes (lightweight, not stored — returned as dicts)
# ---------------------------------------------------------------------------

class EntityRollup:
    """Spend summary for one legal entity."""
    __slots__ = ("entity_id", "entity_name", "total_spend", "addressable_spend",
                 "intercompany_spend", "line_count", "categories", "suppliers")

    def __init__(self, entity_id: str, entity_name: str) -> None:
        self.entity_id = entity_id
        self.entity_name = entity_name
        self.total_spend: float = 0.0
        self.addressable_spend: float = 0.0
        self.intercompany_spend: float = 0.0
        self.line_count: int = 0
        self.categories: Dict[str, float] = {}
        self.suppliers: Dict[str, float] = {}

    def add(self, line: NormalizedSpendLine) -> None:
        self.total_spend += line.amount
        self.line_count += 1
        if line.is_addressable:
            self.addressable_spend += line.amount
        if line.related_party_flag or line.is_intercompany:
            self.intercompany_spend += line.amount
        cat = line.category_name or line.category_id or "Unclassified"
        self.categories[cat] = self.categories.get(cat, 0.0) + line.amount
        sup = line.supplier or "Unknown"
        self.suppliers[sup] = self.suppliers.get(sup, 0.0) + line.amount

    def to_dict(self) -> Dict[str, Any]:
        top_cats = sorted(self.categories.items(), key=lambda x: -x[1])[:10]
        top_sups = sorted(self.suppliers.items(), key=lambda x: -x[1])[:10]
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "total_spend": round(self.total_spend, 2),
            "addressable_spend": round(self.addressable_spend, 2),
            "intercompany_spend": round(self.intercompany_spend, 2),
            "line_count": self.line_count,
            "top_categories": [{"name": k, "amount": round(v, 2)} for k, v in top_cats],
            "top_suppliers": [{"name": k, "amount": round(v, 2)} for k, v in top_sups],
        }


class CompletenessReport:
    """Coverage of expected entities vs. entities with actual spend data."""

    def __init__(self, expected: List[str], observed: List[str]) -> None:
        self.expected = set(expected)
        self.observed = set(observed)

    @property
    def coverage_pct(self) -> float:
        if not self.expected:
            return 100.0
        return round(len(self.expected & self.observed) / len(self.expected) * 100, 1)

    @property
    def missing_entities(self) -> List[str]:
        return sorted(self.expected - self.observed)

    @property
    def unexpected_entities(self) -> List[str]:
        return sorted(self.observed - self.expected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected_entity_count": len(self.expected),
            "observed_entity_count": len(self.observed),
            "coverage_pct": self.coverage_pct,
            "missing_entities": self.missing_entities,
            "unexpected_entities": self.unexpected_entities,
        }


# ---------------------------------------------------------------------------
# ConsolidationEngine
# ---------------------------------------------------------------------------

class ConsolidationEngine:
    """Multi-entity consolidation with intercompany elimination."""

    def __init__(self, entity_tree: Optional[EntityTree] = None) -> None:
        self._tree = entity_tree

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def aggregate_by_entity(
        self, lines: List[NormalizedSpendLine]
    ) -> Dict[str, EntityRollup]:
        """Group and sum spend by legal_entity_id."""
        rollups: Dict[str, EntityRollup] = {}
        entity_names = self._build_entity_name_map()

        for line in lines:
            eid = line.legal_entity_id or "unassigned"
            if eid not in rollups:
                name = entity_names.get(eid, eid)
                rollups[eid] = EntityRollup(eid, name)
            rollups[eid].add(line)

        logger.info(
            '"consolidation_aggregate entities=%d total_lines=%d"',
            len(rollups), len(lines),
        )
        return rollups

    def eliminate_intercompany(
        self, lines: List[NormalizedSpendLine]
    ) -> List[NormalizedSpendLine]:
        """Return lines with intercompany transactions marked as eliminated.

        Uses entity_tree to confirm both parties are within the group.
        Falls back to related_party_flag when entity tree is unavailable.
        """
        result: List[NormalizedSpendLine] = []
        eliminated_count = 0
        eliminated_amount = 0.0

        for line in lines:
            should_eliminate = self._should_eliminate(line)
            if should_eliminate and not line.consolidation_eliminated:
                line = line.model_copy(update={
                    "consolidation_eliminated": True,
                    "is_intercompany": True,
                })
                eliminated_count += 1
                eliminated_amount += line.amount
            result.append(line)

        logger.info(
            '"consolidation_ic_eliminated count=%d amount=%.2f"',
            eliminated_count, eliminated_amount,
        )
        return result

    def validate_completeness(
        self, lines: List[NormalizedSpendLine]
    ) -> CompletenessReport:
        """Compare observed entity IDs to expected IDs from entity tree."""
        expected = self._tree.get_entity_ids() if self._tree else []
        observed = list({ln.legal_entity_id for ln in lines if ln.legal_entity_id})
        return CompletenessReport(expected, observed)

    def consolidate(self, lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
        """Produce a full consolidated spend report.

        Steps:
        1. Eliminate intercompany
        2. Aggregate by entity
        3. Produce group-level rollup (non-eliminated lines only)
        4. Check completeness
        5. Return structured report
        """
        # Step 1: eliminate intercompany
        lines_clean = self.eliminate_intercompany(lines)

        # Step 2: entity-level rollup
        entity_rollups = self.aggregate_by_entity(lines_clean)

        # Step 3: group-level rollup (non-eliminated only)
        active_lines = [ln for ln in lines_clean if not ln.consolidation_eliminated]
        group_total = sum(ln.amount for ln in active_lines)
        group_addressable = sum(ln.amount for ln in active_lines if ln.is_addressable)
        ic_total = sum(ln.amount for ln in lines if ln.related_party_flag or ln.is_intercompany)

        # Step 4: completeness
        completeness = self.validate_completeness(lines)

        # Step 5: category breakdown at group level
        category_totals: Dict[str, float] = defaultdict(float)
        for line in active_lines:
            cat = line.category_name or line.category_id or "Unclassified"
            category_totals[cat] += line.amount

        top_categories = sorted(category_totals.items(), key=lambda x: -x[1])[:15]

        report = {
            "group_total_spend": round(group_total, 2),
            "group_addressable_spend": round(group_addressable, 2),
            "intercompany_eliminated": round(ic_total, 2),
            "addressable_pct": round(group_addressable / group_total * 100, 1) if group_total else 0.0,
            "entity_count": len(entity_rollups),
            "total_lines": len(lines),
            "active_lines": len(active_lines),
            "completeness": completeness.to_dict(),
            "entities": [r.to_dict() for r in entity_rollups.values()],
            "top_categories": [{"name": k, "amount": round(v, 2)} for k, v in top_categories],
        }
        logger.info(
            '"consolidation_complete group_total=%.2f ic_eliminated=%.2f addressable_pct=%.1f"',
            group_total, ic_total, report["addressable_pct"],
        )
        return report

    def entity_comparison(
        self, lines: List[NormalizedSpendLine]
    ) -> Dict[str, Any]:
        """Side-by-side entity comparison for multi-entity CFO view."""
        rollups = self.aggregate_by_entity(lines)
        total_group = sum(r.total_spend for r in rollups.values())
        entities_sorted = sorted(rollups.values(), key=lambda r: -r.total_spend)
        return {
            "group_total": round(total_group, 2),
            "entities": [
                {
                    **r.to_dict(),
                    "share_of_group_pct": round(r.total_spend / total_group * 100, 1) if total_group else 0.0,
                }
                for r in entities_sorted
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_entity_name_map(self) -> Dict[str, str]:
        if not self._tree:
            return {}
        return {n.entity_id: n.entity_name for n in self._tree.nodes}

    def _should_eliminate(self, line: NormalizedSpendLine) -> bool:
        """True when this line should be eliminated from consolidated view."""
        if line.related_party_flag or line.is_intercompany:
            return True
        if self._tree and line.legal_entity_id:
            entity_ids = self._tree.get_entity_ids()
            if line.legal_entity_id in entity_ids:
                # If supplier is also an entity in the group → intercompany
                sup_gstin = line.vendor_gstin or line.gstin
                if sup_gstin:
                    for node in self._tree.nodes:
                        if node.gstin == sup_gstin and node.entity_id != line.legal_entity_id:
                            return True
        return False
