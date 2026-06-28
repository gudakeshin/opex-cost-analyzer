import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Card } from '../components/Common/Card';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { PalettePanel } from '../components/PageComponents/Workbench/PalettePanel';
import { AssumptionsPanel } from '../components/PageComponents/Workbench/AssumptionsPanel';
import { DraftRunCanvas } from '../components/PageComponents/Workbench/DraftRunCanvas';
import { ResultsBoard } from '../components/PageComponents/Workbench/ResultsBoard';
import { RunCompareView } from '../components/PageComponents/Workbench/RunCompareView';
import { RunDetail } from '../components/PageComponents/Workbench/RunDetail';
import { apiGet, apiPost, apiDelete, getApiErrorMessage } from '../hooks/useApi';
import { useSession } from '../context/SessionContext';
import type {
  WorkbenchCatalog,
  WorkbenchRun,
  WorkbenchValidation,
  WorkbenchAssumptionField,
} from '../types';

const CURRENCY = 'INR';

function buildOverrides(
  values: Record<string, string>,
  fields: WorkbenchAssumptionField[],
): Record<string, number | string> {
  const out: Record<string, number | string> = {};
  for (const f of fields) {
    const raw = (values[f.key] ?? '').trim();
    if (raw === '') continue;
    if (f.type === 'text') {
      out[f.key] = raw;
    } else if (f.type === 'percent') {
      const n = Number(raw);
      if (Number.isFinite(n)) out[f.key] = n / 100;
    } else if (f.type === 'int') {
      const n = parseInt(raw, 10);
      if (Number.isFinite(n)) out[f.key] = n;
    } else {
      const n = Number(raw);
      if (Number.isFinite(n)) out[f.key] = n;
    }
  }
  return out;
}

function overridesToFormValues(
  overrides: Record<string, unknown>,
  fields: WorkbenchAssumptionField[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    const v = overrides[f.key];
    if (v === undefined || v === null) continue;
    out[f.key] = f.type === 'percent' ? String(Number(v) * 100) : String(v);
  }
  return out;
}

export const Workbench: React.FC = () => {
  const { sessionId, engagementId, ensureSession } = useSession();
  const [activeSid, setActiveSid] = useState<string | null>(sessionId);
  const [catalog, setCatalog] = useState<WorkbenchCatalog | null>(null);
  const [hydrating, setHydrating] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string[]>([]);
  const [overrideValues, setOverrideValues] = useState<Record<string, string>>({});
  const [runName, setRunName] = useState('');
  const [validation, setValidation] = useState<WorkbenchValidation | null>(null);
  const [running, setRunning] = useState(false);
  const [parentRunId, setParentRunId] = useState<string | null>(null);
  const [seedFromRunId, setSeedFromRunId] = useState<string | null>(null);
  const [seedName, setSeedName] = useState<string | null>(null);

  const [runs, setRuns] = useState<WorkbenchRun[]>([]);
  const [openRun, setOpenRun] = useState<WorkbenchRun | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [includeQualityGates, setIncludeQualityGates] = useState(false);
  const [includeLightReflect, setIncludeLightReflect] = useState(false);
  const [progressMessage, setProgressMessage] = useState('');
  const [promoting, setPromoting] = useState(false);

  const validateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---- Hydration: ensure a session, load catalog + board ------------------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sid = sessionId || (await ensureSession());
        if (cancelled) return;
        setActiveSid(sid);
        const cat = await apiGet<WorkbenchCatalog>('/api/v1/workbench/catalog');
        if (cancelled) return;
        setCatalog(cat);
      } catch (e) {
        if (!cancelled) setError(getApiErrorMessage(e));
      } finally {
        if (!cancelled) setHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRuns = useCallback(async () => {
    const params = engagementId
      ? `engagement_id=${engagementId}`
      : activeSid
        ? `session_id=${activeSid}`
        : '';
    if (!params) return;
    try {
      const res = await apiGet<{ runs: WorkbenchRun[] }>(`/api/v1/workbench/runs?${params}`);
      setRuns(res.runs);
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  }, [engagementId, activeSid]);

  useEffect(() => {
    if (!hydrating) loadRuns();
  }, [hydrating, loadRuns]);

  // ---- Live validation (debounced) ----------------------------------------
  useEffect(() => {
    if (!catalog || !activeSid) return;
    if (selected.length === 0) {
      setValidation(null);
      return;
    }
    if (validateTimer.current) clearTimeout(validateTimer.current);
    validateTimer.current = setTimeout(async () => {
      try {
        const res = await apiPost<WorkbenchValidation>('/api/v1/workbench/preview', {
          session_id: activeSid,
          selected_skills: selected,
          overrides: buildOverrides(overrideValues, catalog.assumptions),
        });
        setValidation(res);
      } catch (e) {
        setError(getApiErrorMessage(e));
      }
    }, 400);
    return () => {
      if (validateTimer.current) clearTimeout(validateTimer.current);
    };
  }, [selected, overrideValues, catalog, activeSid]);

  const relevantKeys = useMemo(() => {
    const keys = new Set<string>();
    if (!catalog) return keys;
    const selSet = new Set(selected);
    for (const skill of catalog.skills) {
      if (selSet.has(skill.name)) skill.params.forEach((p) => keys.add(p));
    }
    return keys;
  }, [catalog, selected]);

  const toggleSkill = (name: string) =>
    setSelected((prev) => (prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]));

  const clearDraft = () => {
    setSelected([]);
    setRunName('');
    setParentRunId(null);
    setSeedFromRunId(null);
    setSeedName(null);
    setValidation(null);
  };

  const handleRun = async () => {
    if (!activeSid || !catalog || selected.length === 0) return;
    const runId = crypto.randomUUID();
    setRunning(true);
    setError(null);
    setProgressMessage('Starting run…');

    progressTimer.current = setInterval(async () => {
      try {
        const prog = await apiGet<{ steps?: { message?: string }[]; phase?: string }>(
          `/api/v1/workbench/progress/${runId}`,
        );
        const last = prog.steps?.[prog.steps.length - 1];
        setProgressMessage(last?.message || prog.phase || 'Running…');
      } catch {
        /* progress not ready yet */
      }
    }, 800);

    try {
      const run = await apiPost<WorkbenchRun>('/api/v1/workbench/runs', {
        session_id: activeSid,
        run_id: runId,
        name: runName || `Run ${runs.length + 1}`,
        selected_skills: selected,
        overrides: buildOverrides(overrideValues, catalog.assumptions),
        engagement_id: engagementId,
        parent_run_id: parentRunId,
        seed_from_run_id: seedFromRunId,
        include_quality_gates: includeQualityGates,
        include_light_reflect: includeLightReflect,
      });
      setRuns((prev) => [run, ...prev]);
      setRunName('');
      setParentRunId(null);
      setSeedFromRunId(null);
      setSeedName(null);
      setProgressMessage('');
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      if (progressTimer.current) clearInterval(progressTimer.current);
      setRunning(false);
      setProgressMessage('');
    }
  };

  const handlePromote = async (run: WorkbenchRun) => {
    setPromoting(true);
    setError(null);
    try {
      const res = await apiPost<{ count: number; promoted: { initiative_id: string }[] }>(
        `/api/v1/workbench/runs/${run.run_id}/promote`,
        {},
      );
      setRuns((prev) =>
        prev.map((r) =>
          r.run_id === run.run_id
            ? { ...r, promoted_initiative_ids: res.promoted.map((p) => p.initiative_id) }
            : r,
        ),
      );
      setOpenRun((prev) =>
        prev?.run_id === run.run_id
          ? { ...prev, promoted_initiative_ids: res.promoted.map((p) => p.initiative_id) }
          : prev,
      );
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setPromoting(false);
    }
  };

  const loadComposition = (run: WorkbenchRun, mode: 'branch' | 'chain') => {
    if (!catalog) return;
    setOpenRun(null);
    if (mode === 'branch') {
      setSelected(run.selected_skills);
      setOverrideValues(overridesToFormValues(run.overrides, catalog.assumptions));
      setRunName(`${run.name} (branch)`);
      setParentRunId(run.run_id);
      setSeedFromRunId(null);
      setSeedName(null);
    } else {
      // chain: build downstream on top of this run's outputs
      setSelected([]);
      setRunName(`${run.name} → next`);
      setSeedFromRunId(run.run_id);
      setSeedName(run.name);
      setParentRunId(run.run_id);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleDelete = async (run: WorkbenchRun) => {
    try {
      await apiDelete(`/api/v1/workbench/runs/${run.run_id}`);
      setRuns((prev) => prev.filter((r) => r.run_id !== run.run_id));
      setCompareIds((prev) => prev.filter((id) => id !== run.run_id));
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const toggleCompare = (runId: string) =>
    setCompareIds((prev) =>
      prev.includes(runId) ? prev.filter((id) => id !== runId) : [...prev, runId].slice(-2),
    );

  const compareRuns = useMemo(() => {
    if (compareIds.length !== 2) return null;
    const a = runs.find((r) => r.run_id === compareIds[0]);
    const b = runs.find((r) => r.run_id === compareIds[1]);
    return a && b ? ([a, b] as [WorkbenchRun, WorkbenchRun]) : null;
  }, [compareIds, runs]);

  if (hydrating) {
    return (
      <MainLayout title="Workbench">
        <Loader label="Loading workbench…" />
      </MainLayout>
    );
  }

  return (
    <MainLayout title="Workbench">
      <PageHeader
        title="Analysis Workbench"
        subtitle="Compose analyses, tweak assumptions, run, and compare"
        sessionId={activeSid}
      />

      {!engagementId && (
        <Alert variant="info" title="Session-scoped board" className="mb-4">
          No engagement context — runs are listed per session. Set an engagement for portfolio-wide boards.
        </Alert>
      )}

      {error && (
        <Alert variant="error" title="Something went wrong" onDismiss={() => setError(null)} className="mb-4">
          {error}
        </Alert>
      )}

      {!catalog ? (
        <Loader label="Loading catalog…" />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
          {/* Palette */}
          <Card title="Analyses" className="h-fit">
            <PalettePanel catalog={catalog} selected={selected} onToggle={toggleSkill} />
          </Card>

          {/* Draft + board */}
          <div className="space-y-4">
            <Card title="Draft run">
              {seedName && (
                <div className="mb-3 text-xs text-deloitte-green bg-green-50 border border-green-200 rounded px-2 py-1">
                  Chaining on top of <strong>{seedName}</strong> — pick downstream analyses to add.
                </div>
              )}
              <AssumptionsPanel
                fields={catalog.assumptions}
                values={overrideValues}
                relevantKeys={relevantKeys}
                onChange={(k, v) => setOverrideValues((prev) => ({ ...prev, [k]: v }))}
              />
              <div className="mt-3">
                <DraftRunCanvas
                  selected={selected}
                  validation={validation}
                  runName={runName}
                  running={running}
                  progressMessage={progressMessage}
                  includeQualityGates={includeQualityGates}
                  includeLightReflect={includeLightReflect}
                  onRunNameChange={setRunName}
                  onRemove={(name) => toggleSkill(name)}
                  onRun={handleRun}
                  onClear={clearDraft}
                  onQualityGatesChange={setIncludeQualityGates}
                  onLightReflectChange={setIncludeLightReflect}
                />
              </div>
            </Card>

            <Card title={`Results board${runs.length ? ` (${runs.length})` : ''}`}>
              {compareIds.length === 1 && (
                <p className="text-xs text-brand-muted mb-2">Select one more run to compare.</p>
              )}
              <ResultsBoard
                runs={runs}
                currency={CURRENCY}
                compareIds={compareIds}
                onOpen={setOpenRun}
                onBranch={(r) => loadComposition(r, 'branch')}
                onChain={(r) => loadComposition(r, 'chain')}
                onDelete={handleDelete}
                onToggleCompare={toggleCompare}
              />
            </Card>
          </div>
        </div>
      )}

      {openRun && (
        <RunDetail
          run={openRun}
          currency={CURRENCY}
          onClose={() => setOpenRun(null)}
          onBranch={(r) => loadComposition(r, 'branch')}
          onChain={(r) => loadComposition(r, 'chain')}
          onPromote={handlePromote}
          promoting={promoting}
        />
      )}

      {compareRuns && (
        <RunCompareView runs={compareRuns} currency={CURRENCY} onClose={() => setCompareIds([])} />
      )}
    </MainLayout>
  );
};

export default Workbench;
