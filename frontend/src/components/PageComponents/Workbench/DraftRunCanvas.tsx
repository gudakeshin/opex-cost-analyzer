import React from 'react';
import { Button } from '../../Common/Button';
import type { WorkbenchValidation } from '../../../types';

interface DraftRunCanvasProps {
  selected: string[];
  validation: WorkbenchValidation | null;
  runName: string;
  running: boolean;
  progressMessage?: string;
  includeQualityGates: boolean;
  includeLightReflect: boolean;
  onRunNameChange: (value: string) => void;
  onRemove: (name: string) => void;
  onRun: () => void;
  onClear: () => void;
  onQualityGatesChange: (v: boolean) => void;
  onLightReflectChange: (v: boolean) => void;
}

function prettyName(name: string): string {
  return name
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export const DraftRunCanvas: React.FC<DraftRunCanvasProps> = ({
  selected,
  validation,
  runName,
  running,
  progressMessage,
  includeQualityGates,
  includeLightReflect,
  onRunNameChange,
  onRemove,
  onRun,
  onClear,
  onQualityGatesChange,
  onLightReflectChange,
}) => {
  const addedDeps = new Set(validation?.added_deps ?? []);
  const blocked = validation?.blocked ?? false;
  const canRun = selected.length > 0 && !blocked && !running;

  return (
    <div className="space-y-3">
      <input
        type="text"
        value={runName}
        onChange={(e) => onRunNameChange(e.target.value)}
        placeholder="Name this run (e.g. Base case, WACC 13%)"
        className="w-full px-3 py-2 rounded-lg border border-brand-border text-sm font-medium focus:outline-none focus:ring-1 focus:ring-deloitte-green"
      />

      {selected.length === 0 ? (
        <p className="text-sm text-brand-muted py-6 text-center border border-dashed border-brand-border rounded-lg">
          Pick analyses from the palette to compose a run.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((name) => (
            <span
              key={name}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-green-50 border border-deloitte-green text-xs text-brand-ink"
            >
              {prettyName(name)}
              <button
                type="button"
                onClick={() => onRemove(name)}
                className="text-brand-muted hover:text-error"
                aria-label={`Remove ${name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {addedDeps.size > 0 && (
        <div className="text-xs text-brand-muted">
          <span className="font-medium">Auto-added prerequisites: </span>
          {[...addedDeps].map((d) => prettyName(d)).join(', ')}
        </div>
      )}

      {validation && validation.blocking_errors.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-2 space-y-1">
          {validation.blocking_errors.map((e, i) => (
            <p key={i} className="text-xs text-red-800">
              ⛔ {e.message}
            </p>
          ))}
        </div>
      )}

      {validation && validation.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 space-y-1">
          {validation.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-800">
              ⚠ {w.message}
            </p>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2 text-xs text-brand-muted">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeQualityGates}
            onChange={(e) => onQualityGatesChange(e.target.checked)}
            disabled={running}
          />
          Include quality gates (data-quality-gate, sme-critique when eligible)
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeLightReflect}
            onChange={(e) => onLightReflectChange(e.target.checked)}
            disabled={running}
          />
          Light synthesis summary after run
        </label>
      </div>

      {running && progressMessage && (
        <p className="text-xs text-deloitte-green animate-pulse">{progressMessage}</p>
      )}

      <div className="flex items-center justify-between pt-1">
        <span className="text-xs text-brand-muted">
          {validation?.resolved_skills?.length ?? selected.length} analyses
          {validation?.estimated_duration ? ` · ${validation.estimated_duration}` : ''}
        </span>
        <div className="flex gap-2">
          {selected.length > 0 && (
            <Button variant="ghost" onClick={onClear} disabled={running}>
              Clear
            </Button>
          )}
          <Button variant="primary" onClick={onRun} loading={running} disabled={!canRun}>
            Run analysis
          </Button>
        </div>
      </div>
    </div>
  );
};
