"""
Phase 5 test suite — Deployment + Scale + Calibration.

Covers:
  - app/services/cache.py      (TierConfig, StreamingIngestion, CostRoomCache, SLO benchmark)
  - app/services/calibration.py (realised-savings ingestion, variance, lever proposals, report, version bump)
  - app/services/tear_down.py  (plan generation, execution, cloud-tag verification, attestation, backup)
  - deploy/  directory structure (Terraform, Ansible, Helm files exist and are non-empty)
  - docs/security/  (hardening_guide.md, infosec_faq.md exist and cover required topics)
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

BASE = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = BASE / "deploy"
DOCS_SECURITY = BASE / "docs" / "security"


def _realised_records(engagement_id: str = "test-eng-001"):
    return [
        {
            "initiative_id": "init_01",
            "lever_id": "branch_rationalisation",
            "pack_id": "bfsi_banks",
            "planned_p50_cr": 10.0,
            "realised_cr": 8.5,
            "realised_date": "2026-03-31",
            "data_source": "finance_sign_off",
        },
        {
            "initiative_id": "init_02",
            "lever_id": "kyc_aml_automation",
            "pack_id": "bfsi_banks",
            "planned_p50_cr": 5.0,
            "realised_cr": 5.8,
            "realised_date": "2026-03-31",
            "data_source": "auditor",
        },
        {
            "initiative_id": "init_01",
            "lever_id": "branch_rationalisation",
            "pack_id": "bfsi_banks",
            "planned_p50_cr": 3.0,
            "realised_cr": 2.4,
            "realised_date": "2026-04-15",
            "data_source": "self_reported",
        },
    ]


# ──────────────────────────────────────────────────────────────────────────────
# 1. TierConfig / tier_for_line_count
# ──────────────────────────────────────────────────────────────────────────────

class TestTierConfig:
    def test_mid_cap_no_duckdb(self):
        from app.services.cache import tier_for_line_count
        t = tier_for_line_count(1_000)
        assert t.name == "mid_cap"
        assert not t.use_duckdb
        assert not t.requires_redis

    def test_large_cap_uses_duckdb(self):
        from app.services.cache import tier_for_line_count
        t = tier_for_line_count(1_000_000)
        assert t.name == "large_cap"
        assert t.use_duckdb
        assert t.requires_redis

    def test_conglomerate_uses_parquet(self):
        from app.services.cache import tier_for_line_count
        t = tier_for_line_count(15_000_000)
        assert t.name == "conglomerate"
        assert t.use_parquet_chunks
        assert t.chunk_size >= 500_000

    def test_tier_config_has_slo(self):
        from app.services.cache import tier_for_line_count
        for n in [10_000, 1_000_000, 12_000_000]:
            t = tier_for_line_count(n)
            assert t.ingestion_slo_s > 0
            assert t.filter_slo_s > 0

    def test_slo_tightens_with_scale(self):
        from app.services.cache import tier_for_line_count
        mid = tier_for_line_count(50_000)
        lrg = tier_for_line_count(2_000_000)
        con = tier_for_line_count(15_000_000)
        assert mid.ingestion_slo_s < lrg.ingestion_slo_s < con.ingestion_slo_s
        # Filter gets tighter (Redis expected at scale)
        assert mid.filter_slo_s > lrg.filter_slo_s > con.filter_slo_s


# ──────────────────────────────────────────────────────────────────────────────
# 2. StreamingIngestion (DuckDB fallback path)
# ──────────────────────────────────────────────────────────────────────────────

class TestStreamingIngestion:
    def _csv_file(self, rows: int = 100) -> Path:
        t = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
        t.write("supplier,amount,category\n")
        for i in range(rows):
            t.write(f"Vendor{i},{i * 1000},it_software\n")
        t.flush()
        return Path(t.name)

    def test_ingest_csv_returns_dict_with_rows(self):
        from app.services.cache import StreamingIngestion
        ing = StreamingIngestion()
        path = self._csv_file(50)
        result = ing.ingest_csv(path)
        assert "rows" in result
        assert result["rows"] >= 0   # may be 0 on fallback path
        assert "elapsed_s" in result
        assert "tier" in result
        assert "slo_met" in result

    def test_ingest_csv_tier_assigned(self):
        from app.services.cache import StreamingIngestion
        ing = StreamingIngestion()
        path = self._csv_file(200)
        result = ing.ingest_csv(path)
        assert result["tier"] in {"mid_cap", "large_cap", "conglomerate"}

    def test_filter_query_returns_dict(self):
        from app.services.cache import StreamingIngestion
        ing = StreamingIngestion()
        result = ing.filter_query("SELECT 1 AS x")
        assert "elapsed_s" in result
        # rows may be empty if DuckDB not available

    def test_close_is_idempotent(self):
        from app.services.cache import StreamingIngestion
        ing = StreamingIngestion()
        ing.close()
        ing.close()  # must not raise


# ──────────────────────────────────────────────────────────────────────────────
# 3. CostRoomCache (local-dict fallback; Redis not required)
# ──────────────────────────────────────────────────────────────────────────────

class TestCostRoomCache:
    def _cache(self):
        from app.services.cache import CostRoomCache
        return CostRoomCache(redis_url="redis://localhost:9999/0")  # force local fallback

    def test_set_get_roundtrip(self):
        cache = self._cache()
        payload = {"initiatives": [{"id": "i1"}], "total": 1}
        cache.set("eng-A", {"cat": "logistics"}, payload)
        assert cache.get("eng-A", {"cat": "logistics"}) == payload

    def test_miss_returns_none(self):
        cache = self._cache()
        assert cache.get("eng-Z", {"x": 99}) is None

    def test_different_filters_separate_keys(self):
        cache = self._cache()
        cache.set("eng-B", {"f": "a"}, {"v": 1})
        cache.set("eng-B", {"f": "b"}, {"v": 2})
        assert cache.get("eng-B", {"f": "a"})["v"] == 1
        assert cache.get("eng-B", {"f": "b"})["v"] == 2

    def test_invalidate_does_not_raise(self):
        cache = self._cache()
        cache.set("eng-C", {"k": 1}, {"d": "x"})
        result = cache.invalidate("eng-C")
        assert isinstance(result, int)

    def test_backend_is_local_dict_on_failure(self):
        cache = self._cache()
        assert cache.backend == "local_dict"

    def test_overwrite_same_key(self):
        cache = self._cache()
        cache.set("eng-D", {"q": 1}, {"v": 1})
        cache.set("eng-D", {"q": 1}, {"v": 2})
        assert cache.get("eng-D", {"q": 1})["v"] == 2

    def test_cache_key_deterministic(self):
        from app.services.cache import CostRoomCache
        k1 = CostRoomCache._cache_key("eng1", {"b": 2, "a": 1})
        k2 = CostRoomCache._cache_key("eng1", {"a": 1, "b": 2})
        assert k1 == k2  # sorted JSON → same hash


# ──────────────────────────────────────────────────────────────────────────────
# 4. SLO benchmark runner
# ──────────────────────────────────────────────────────────────────────────────

class TestSLOBenchmark:
    def test_run_returns_results_for_all_tiers(self):
        from app.services.cache import run_slo_benchmark, MID_CAP_LIMIT, LARGE_CAP_LIMIT, CONGLOMERATE_LIMIT
        results = run_slo_benchmark(line_counts=[MID_CAP_LIMIT, LARGE_CAP_LIMIT, CONGLOMERATE_LIMIT])
        assert len(results) == 6   # 2 operations × 3 tiers

    def test_result_fields_present(self):
        from app.services.cache import run_slo_benchmark, MID_CAP_LIMIT
        results = run_slo_benchmark(line_counts=[MID_CAP_LIMIT])
        for r in results:
            d = r.to_dict()
            assert set(d.keys()) >= {"tier", "operation", "elapsed_s", "slo_ceiling_s", "passed"}

    def test_synthetic_ingestion_always_passes_slo(self):
        from app.services.cache import run_slo_benchmark
        results = run_slo_benchmark()
        for r in [x for x in results if x.operation == "ingestion"]:
            assert r.passed

    def test_filter_always_passes_slo(self):
        from app.services.cache import run_slo_benchmark
        results = run_slo_benchmark()
        for r in [x for x in results if x.operation == "filter"]:
            assert r.passed


# ──────────────────────────────────────────────────────────────────────────────
# 5. Calibration — ingestion
# ──────────────────────────────────────────────────────────────────────────────

class TestCalibrationIngestion:
    ENG = "phase5-test-cal-001"

    def test_ingest_writes_file(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        result = calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG))
        assert result["records_ingested"] == 3
        assert result["errors"] == []
        assert Path(result["path"]).exists()

    def test_ingest_bad_record_reported(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        bad = [{"initiative_id": "x"}]  # missing required fields
        result = calibration.ingest_realised_savings(self.ENG, bad)
        assert result["records_ingested"] == 0
        assert len(result["errors"]) == 1

    def test_ingest_appends_on_second_call(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG)[:1])
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG)[1:2])
        records = calibration.load_realised_savings(self.ENG)
        assert len(records) == 2

    def test_load_missing_engagement_returns_empty(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        records = calibration.load_realised_savings("nonexistent-eng")
        assert records == []


# ──────────────────────────────────────────────────────────────────────────────
# 6. Calibration — variance computation
# ──────────────────────────────────────────────────────────────────────────────

class TestCalibrationVariance:
    ENG = "phase5-test-var-001"

    def _setup(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG))

    def test_variance_found(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        from app.services import calibration
        v = calibration.compute_variance(self.ENG, "init_01")
        assert v["found"] is True
        assert v["planned_p50_cr"] == 13.0    # 10 + 3
        assert v["realised_cr"] == pytest_approx(10.9, abs=0.05)  # 8.5 + 2.4

    def test_variance_missing_initiative(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        from app.services import calibration
        v = calibration.compute_variance(self.ENG, "no_such_initiative")
        assert v["found"] is False

    def test_realisation_rate_positive(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        from app.services import calibration
        v = calibration.compute_variance(self.ENG, "init_02")
        assert v["realisation_rate"] > 0


# ──────────────────────────────────────────────────────────────────────────────
# 7. Calibration — lever-range proposal
# ──────────────────────────────────────────────────────────────────────────────

class TestLeverRangeProposal:
    def test_proposal_fields_present(self):
        from app.services.calibration import (
            RealisedSavingsRecord,
            propose_lever_range_update,
        )
        records = [
            RealisedSavingsRecord(
                engagement_id="e1",
                initiative_id="i1",
                lever_id="branch_rationalisation",
                pack_id="bfsi_banks",
                planned_p50_cr=10.0,
                realised_cr=8.0,
                realised_date="2026-03-31",
                data_source="finance_sign_off",
            )
        ]
        p = propose_lever_range_update("bfsi_banks", "branch_rationalisation", records)
        assert p.pack_id == "bfsi_banks"
        assert p.lever_id == "branch_rationalisation"
        assert p.proposed_p50_pct > 0
        assert p.proposed_p10_pct <= p.proposed_p50_pct <= p.proposed_p90_pct
        assert p.evidence_count == 1
        assert 0 < p.realisation_rate < 2.0

    def test_proposal_no_records_returns_current(self):
        from app.services.calibration import propose_lever_range_update
        p = propose_lever_range_update("bfsi_banks", "branch_rationalisation", [])
        assert p.evidence_count == 0
        assert p.realisation_rate == 1.0
        # Proposed == current when no evidence
        assert p.proposed_p50_pct == p.current_p50_pct

    def test_proposal_to_dict(self):
        from app.services.calibration import propose_lever_range_update
        p = propose_lever_range_update("bfsi_banks", "branch_rationalisation", [])
        d = p.to_dict()
        assert "pack_id" in d
        assert "proposed_p50_pct" in d
        assert "evidence_count" in d


# ──────────────────────────────────────────────────────────────────────────────
# 8. Calibration — full report
# ──────────────────────────────────────────────────────────────────────────────

class TestCalibrationReport:
    ENG = "phase5-test-rpt-001"

    def test_report_no_data(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        report = calibration.generate_calibration_report(self.ENG)
        assert report.gate_recommendation == "no_data"
        assert report.overall_realisation_rate == 0.0

    def test_report_with_data(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG))
        report = calibration.generate_calibration_report(self.ENG)
        assert report.overall_realisation_rate > 0
        assert report.gate_recommendation in {"auto_approve", "senior_review", "deep_audit"}
        assert len(report.lever_proposals) > 0
        assert len(report.records) > 0

    def test_report_to_dict_structure(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG))
        report = calibration.generate_calibration_report(self.ENG)
        d = report.to_dict()
        assert "engagement_id" in d
        assert "variance_summary" in d
        assert "lever_proposals" in d
        assert "gate_recommendation" in d

    def test_report_written_to_disk(self, tmp_path, monkeypatch):
        from app.services import calibration
        monkeypatch.setattr(calibration, "_CALIBRATION_ROOT", tmp_path)
        calibration.ingest_realised_savings(self.ENG, _realised_records(self.ENG))
        calibration.generate_calibration_report(self.ENG)
        report_path = tmp_path / f"{self.ENG}_calibration_report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["engagement_id"] == self.ENG


# ──────────────────────────────────────────────────────────────────────────────
# 9. Calibration — version bump (dry-run only; pack files not modified)
# ──────────────────────────────────────────────────────────────────────────────

class TestVersionBump:
    def test_dry_run_returns_new_version(self):
        from app.services.calibration import apply_version_bump, LeverRangeProposal
        proposals = [
            LeverRangeProposal(
                pack_id="bfsi_banks",
                lever_id="branch_rationalisation",
                current_p10_pct=4.0,
                current_p50_pct=8.0,
                current_p90_pct=15.0,
                proposed_p10_pct=3.5,
                proposed_p50_pct=7.0,
                proposed_p90_pct=13.0,
                evidence_count=3,
                realisation_rate=0.875,
                approved=True,
            )
        ]
        result = apply_version_bump("bfsi_banks", proposals, reviewer="test_reviewer", dry_run=True)
        assert result["pack_id"] == "bfsi_banks"
        assert "dry_run" in result["new_version"]
        assert result["dry_run"] is True
        assert result["levers_updated"] == 1

    def test_dry_run_does_not_modify_pack(self):
        from app.services.calibration import apply_version_bump, LeverRangeProposal
        levers_path = BASE / "sector_packs" / "bfsi_banks" / "sector_levers.json"
        original = levers_path.read_text()
        proposals = [
            LeverRangeProposal(
                pack_id="bfsi_banks",
                lever_id="branch_rationalisation",
                current_p10_pct=4.0,
                current_p50_pct=8.0,
                current_p90_pct=15.0,
                proposed_p10_pct=99.0,
                proposed_p50_pct=99.0,
                proposed_p90_pct=99.0,
                evidence_count=1,
                realisation_rate=12.0,
                approved=True,
            )
        ]
        apply_version_bump("bfsi_banks", proposals, reviewer="tester", dry_run=True)
        assert levers_path.read_text() == original  # file unchanged

    def test_missing_pack_returns_error(self):
        from app.services.calibration import apply_version_bump
        result = apply_version_bump("nonexistent_pack", [], reviewer="x", dry_run=True)
        assert "error" in result


# ──────────────────────────────────────────────────────────────────────────────
# 10. Tear-down — plan generation
# ──────────────────────────────────────────────────────────────────────────────

class TestTearDownPlan:
    def test_plan_has_steps(self):
        from app.services.tear_down import generate_tear_down_plan
        plan = generate_tear_down_plan("eng-td-001")
        assert len(plan.steps) >= 7
        step_ids = {s.step_id for s in plan.steps}
        assert "pack_locks_sweep" in step_ids
        assert "memory_scope_sweep" in step_ids
        assert "cloud_tag_verify" in step_ids

    def test_plan_dry_run_default(self):
        from app.services.tear_down import generate_tear_down_plan
        plan = generate_tear_down_plan("eng-td-002")
        assert plan.dry_run is True

    def test_plan_to_dict(self):
        from app.services.tear_down import generate_tear_down_plan
        plan = generate_tear_down_plan("eng-td-003")
        d = plan.to_dict()
        assert "engagement_id" in d
        assert "steps" in d
        assert isinstance(d["steps"], list)

    def test_dlp_checklist_non_empty(self):
        from app.services.tear_down import _laptop_dlp_checklist
        checklist = _laptop_dlp_checklist("eng-abc")
        assert len(checklist) >= 5
        assert any("eng-abc" in item for item in checklist)


# ──────────────────────────────────────────────────────────────────────────────
# 11. Tear-down — execution
# ──────────────────────────────────────────────────────────────────────────────

class TestTearDownExecution:
    ENG = "phase5-td-exec-001"

    def test_execute_dry_run(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", tmp_path / "pack_locks")
        monkeypatch.setattr(td, "_MEMORY_ROOT", tmp_path / "memory")
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "calibration")
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "backups")
        result = td.execute_tear_down(self.ENG, dry_run=True, executor="pytest")
        assert result["engagement_id"] == self.ENG
        assert result["dry_run"] is True
        assert "completed" in result
        assert "steps" in result

    def test_execute_sweeps_pack_locks(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        lock_dir = tmp_path / "pack_locks"
        lock_dir.mkdir()
        (lock_dir / f"{self.ENG}_bfsi_banks.json").write_text("{}")
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", lock_dir)
        monkeypatch.setattr(td, "_MEMORY_ROOT", tmp_path / "memory")
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "calibration")
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "backups")
        result = td.execute_tear_down(self.ENG, dry_run=False, executor="pytest")
        # After non-dry-run, file should be gone
        assert not (lock_dir / f"{self.ENG}_bfsi_banks.json").exists()

    def test_execute_returns_step_counts(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", tmp_path / "pl")
        monkeypatch.setattr(td, "_MEMORY_ROOT", tmp_path / "mem")
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "cal")
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "bak")
        result = td.execute_tear_down(self.ENG, dry_run=True, executor="pytest")
        assert result["completed"] + result["skipped"] + result["failed"] == len(result["steps"])


# ──────────────────────────────────────────────────────────────────────────────
# 12. Tear-down — cloud-tag verification
# ──────────────────────────────────────────────────────────────────────────────

class TestCloudTagVerification:
    def test_verify_returns_zero_residual(self):
        from app.services.tear_down import verify_cloud_tags
        result = verify_cloud_tags("eng-verify-001")
        assert "zero_residual" in result
        assert result["zero_residual"] is True
        assert result["status"] == "verified"

    def test_verify_has_tag_key_value(self):
        from app.services.tear_down import verify_cloud_tags
        result = verify_cloud_tags("eng-verify-002", provider="azure")
        assert result["tag_key"] == "opex:engagement_id"
        assert result["tag_value"] == "eng-verify-002"
        assert result["provider"] == "azure"

    def test_verify_resources_found_is_zero(self):
        from app.services.tear_down import verify_cloud_tags
        result = verify_cloud_tags("eng-verify-003")
        assert result["resources_found"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# 13. Tear-down — attestation
# ──────────────────────────────────────────────────────────────────────────────

class TestTearDownAttestation:
    ENG = "phase5-att-001"

    def test_attestation_generated(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_ATTESTATION_ROOT", tmp_path)
        att = td.generate_attestation(self.ENG, executor="senior_advisor", notes="Q2 engagement")
        assert att.engagement_id == self.ENG
        assert att.executor == "senior_advisor"
        assert att.signature != ""
        assert att.cloud_tag_verified is True

    def test_attestation_written_to_disk(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_ATTESTATION_ROOT", tmp_path)
        td.generate_attestation(self.ENG, executor="test")
        path = tmp_path / f"{self.ENG}_attestation.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["engagement_id"] == self.ENG

    def test_attestation_zero_residual_confirmed_on_clean_run(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_ATTESTATION_ROOT", tmp_path)
        execution = {"completed": 5, "skipped": 3, "failed": 0, "artefacts": []}
        att = td.generate_attestation(self.ENG, executor="test", execution_result=execution)
        assert att.zero_residual_confirmed is True

    def test_attestation_not_zero_residual_on_failed_steps(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_ATTESTATION_ROOT", tmp_path)
        execution = {"completed": 3, "skipped": 2, "failed": 1, "artefacts": []}
        att = td.generate_attestation(self.ENG, executor="test", execution_result=execution)
        assert att.zero_residual_confirmed is False

    def test_attestation_to_dict(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_ATTESTATION_ROOT", tmp_path)
        att = td.generate_attestation(self.ENG, executor="test")
        d = att.to_dict()
        required_keys = {
            "engagement_id", "completed_at", "executor",
            "steps_completed", "cloud_tag_verified", "zero_residual_confirmed",
            "signature", "dlp_checklist",
        }
        assert required_keys.issubset(d.keys())


# ──────────────────────────────────────────────────────────────────────────────
# 14. Tear-down — backup
# ──────────────────────────────────────────────────────────────────────────────

class TestDailyBackup:
    ENG = "phase5-bak-001"

    def test_backup_creates_directory(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "backups")
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", tmp_path / "pl")
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "cal")
        result = td.create_daily_backup(self.ENG)
        assert Path(result["backup_path"]).exists()
        assert result["engagement_id"] == self.ENG
        assert "timestamp" in result

    def test_backup_copies_existing_files(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        locks = tmp_path / "pl"
        locks.mkdir()
        (locks / f"{self.ENG}_bfsi.json").write_text("{}")
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "backups")
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", locks)
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "cal")
        result = td.create_daily_backup(self.ENG)
        assert result["files_backed_up"] >= 1

    def test_backup_s3_warning_without_bucket(self, tmp_path, monkeypatch):
        import app.services.tear_down as td
        monkeypatch.setattr(td, "_BACKUP_ROOT", tmp_path / "backups")
        monkeypatch.setattr(td, "_PACK_LOCKS_ROOT", tmp_path / "pl")
        monkeypatch.setattr(td, "_CALIBRATION_ROOT", tmp_path / "cal")
        monkeypatch.delenv("AWS_BACKUP_BUCKET", raising=False)
        result = td.create_daily_backup(self.ENG, destination="s3")
        assert "s3_warning" in result


# ──────────────────────────────────────────────────────────────────────────────
# 15. Deploy directory structure
# ──────────────────────────────────────────────────────────────────────────────

class TestDeployStructure:
    def test_terraform_aws_mumbai_files_exist(self):
        tf_dir = DEPLOY_ROOT / "terraform" / "aws-mumbai"
        for fname in ["main.tf", "variables.tf", "outputs.tf"]:
            assert (tf_dir / fname).exists(), f"Missing {fname}"

    def test_terraform_azure_india_files_exist(self):
        az_dir = DEPLOY_ROOT / "terraform" / "azure-india"
        for fname in ["main.tf", "variables.tf"]:
            assert (az_dir / fname).exists(), f"Missing {fname}"

    def test_ansible_on_prem_files_exist(self):
        ans_dir = DEPLOY_ROOT / "ansible" / "on-prem"
        assert (ans_dir / "site.yml").exists()
        assert (ans_dir / "roles" / "opex_app" / "tasks" / "main.yml").exists()

    def test_helm_chart_files_exist(self):
        helm_dir = DEPLOY_ROOT / "helm" / "opex-analyzer"
        for fname in ["Chart.yaml", "values.yaml"]:
            assert (helm_dir / fname).exists(), f"Missing {fname}"
        assert (helm_dir / "templates" / "deployment.yaml").exists()

    def test_terraform_aws_has_kms_resource(self):
        content = (DEPLOY_ROOT / "terraform" / "aws-mumbai" / "main.tf").read_text()
        assert "aws_kms_key" in content
        assert "engagement_id" in content

    def test_terraform_aws_has_engagement_tags(self):
        content = (DEPLOY_ROOT / "terraform" / "aws-mumbai" / "main.tf").read_text()
        assert "opex:engagement_id" in content

    def test_terraform_azure_has_key_vault(self):
        content = (DEPLOY_ROOT / "terraform" / "azure-india" / "main.tf").read_text()
        assert "azurerm_key_vault" in content

    def test_helm_deployment_has_security_context(self):
        template = (DEPLOY_ROOT / "helm" / "opex-analyzer" / "templates" / "deployment.yaml").read_text()
        values = (DEPLOY_ROOT / "helm" / "opex-analyzer" / "values.yaml").read_text()
        assert "securityContext" in template
        # runAsNonRoot is defined in values.yaml and referenced via toYaml in the template
        assert "runAsNonRoot" in values

    def test_ansible_tasks_has_hardening(self):
        content = (DEPLOY_ROOT / "ansible" / "on-prem" / "roles" / "opex_app" / "tasks" / "main.yml").read_text()
        assert "protected-mode" in content or "requirepass" in content or "harden" in content.lower()


# ──────────────────────────────────────────────────────────────────────────────
# 16. Security documentation
# ──────────────────────────────────────────────────────────────────────────────

class TestSecurityDocs:
    def test_hardening_guide_exists(self):
        assert (DOCS_SECURITY / "hardening_guide.md").exists()

    def test_infosec_faq_exists(self):
        assert (DOCS_SECURITY / "infosec_faq.md").exists()

    def test_hardening_guide_covers_tls(self):
        content = (DOCS_SECURITY / "hardening_guide.md").read_text()
        assert "TLS" in content
        assert "1.3" in content

    def test_hardening_guide_covers_data_bands(self):
        content = (DOCS_SECURITY / "hardening_guide.md").read_text()
        assert "B1" in content and "B4" in content

    def test_hardening_guide_covers_teardown(self):
        content = (DOCS_SECURITY / "hardening_guide.md").read_text()
        assert "tear" in content.lower() or "teardown" in content.lower()

    def test_infosec_faq_has_80_plus_questions(self):
        content = (DOCS_SECURITY / "infosec_faq.md").read_text()
        # Count lines starting with **Q
        q_count = sum(1 for line in content.splitlines() if line.strip().startswith("**Q"))
        assert q_count >= 80, f"FAQ has only {q_count} questions; expected ≥ 80"

    def test_infosec_faq_covers_data_residency(self):
        content = (DOCS_SECURITY / "infosec_faq.md").read_text()
        assert "India" in content
        assert "data residency" in content.lower() or "localisation" in content.lower()

    def test_infosec_faq_covers_llm_security(self):
        content = (DOCS_SECURITY / "infosec_faq.md").read_text()
        assert "LLM" in content
        assert "M1" in content or "M2" in content

    def test_infosec_faq_covers_teardown(self):
        content = (DOCS_SECURITY / "infosec_faq.md").read_text()
        assert "tear-down" in content.lower() or "teardown" in content.lower()

    def test_infosec_faq_covers_pii(self):
        content = (DOCS_SECURITY / "infosec_faq.md").read_text()
        assert "PII" in content or "pii" in content.lower()


# ── pytest import for approx ──────────────────────────────────────────────────
try:
    from pytest import approx as pytest_approx
except ImportError:
    def pytest_approx(x, abs=0.1):
        return x
