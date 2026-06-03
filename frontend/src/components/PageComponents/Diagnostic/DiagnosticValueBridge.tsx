import React, { useEffect, useId, useMemo, useState } from 'react';
import { formatCr, formatBandRange } from '../../../utils/formatInr';
import {
  valueAtTableCalculationNote,
  valueAtTableRationale,
} from '../../../utils/diagnosticRationale';
import {
  buildDefaultPercentilesByLever,
  mergePercentilesForRows,
  PERCENTILE_DEFAULT,
  PERCENTILE_MAX,
  PERCENTILE_MIN,
  percentileScenarioLabel,
  percentileScenarioShort,
} from '../../../utils/percentileInterpolation';
import {
  buildValueBridgePortfolio,
  buildValueBridgeSegments,
  complexityShortLabel,
  valueBridgeConcentrationLine,
  valueBridgeHowValued,
} from '../../../utils/valueBridge';
import type { ValueAtTableRow } from '../../../types';

interface DiagnosticValueBridgeProps {
  rows: ValueAtTableRow[];
  totalP50Cr?: number;
  annualRevenueCr?: number;
}

const TH_CLASS =
  'py-2.5 px-2 text-left text-xs font-semibold uppercase tracking-wide text-brand-muted border-b border-brand-border';
const TD_CLASS = 'py-3 px-2 text-sm text-brand-ink align-top';
const NUM_CLASS = 'tabular-nums';
const TABLE_COLS = 6;

function DetailBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">{label}</p>
      <p className="mt-0.5 text-sm text-brand-muted leading-relaxed">{text}</p>
    </div>
  );
}

function ComplexityBadge({ tier }: { tier: string | null }) {
  const label = complexityShortLabel(tier);
  if (!label) return null;
  const styles =
    tier === 'low'
      ? 'bg-green-50 text-green-800 border-green-200'
      : tier === 'high'
        ? 'bg-slate-100 text-slate-700 border-slate-200'
        : 'bg-amber-50 text-amber-900 border-amber-200';
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${styles}`}
    >
      {label}
    </span>
  );
}

function LeverUncertaintyControl({
  leverName,
  p10,
  p90,
  percentile,
  scenarioCr,
  onChange,
}: {
  leverName: string;
  p10: number;
  p90: number;
  percentile: number;
  scenarioCr: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const label = percentileScenarioLabel(percentile);

  return (
    <div className="min-w-[168px] space-y-2">
      <div className="flex items-center justify-between gap-2 text-[10px] tabular-nums text-brand-muted">
        <span>P10 {formatCr(p10, { bare: true })}</span>
        <span className="font-semibold text-brand-ink">{percentileScenarioShort(percentile)}</span>
        <span>P90 {formatCr(p90, { bare: true })}</span>
      </div>
      <input
        id={id}
        type="range"
        min={PERCENTILE_MIN}
        max={PERCENTILE_MAX}
        step={1}
        value={percentile}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 accent-brand-green cursor-pointer"
        aria-label={`Uncertainty for ${leverName}`}
        aria-valuemin={PERCENTILE_MIN}
        aria-valuemax={PERCENTILE_MAX}
        aria-valuenow={percentile}
        aria-valuetext={`${label} · ${formatCr(scenarioCr, { bare: true })} Cr/yr`}
      />
      <p className="text-[10px] text-brand-muted leading-snug">
        {formatCr(scenarioCr, { bare: true })} Cr/yr · {label}
      </p>
    </div>
  );
}

function PortfolioBandSummary({
  p10,
  p50,
  p90,
  scenarioCr,
}: {
  p10: number;
  p50: number;
  p90: number;
  scenarioCr: number;
}) {
  const max = Math.max(p90, p50, p10, scenarioCr, 1);
  const leftPct = (p10 / max) * 100;
  const widthPct = Math.max(((p90 - p10) / max) * 100, 2);
  const scenarioPct = (scenarioCr / max) * 100;

  return (
    <div className="space-y-1.5 min-w-[120px]">
      <div
        className="relative h-2.5 w-full rounded-full bg-brand-surface-muted/80"
        role="img"
        aria-label={`Portfolio band ${formatCr(p10, { bare: true })} to ${formatCr(p90, { bare: true })}, combined scenario ${formatCr(scenarioCr, { bare: true })}`}
      >
        <div
          className="absolute inset-y-0 rounded-full bg-brand-green/20 border border-brand-green/25"
          style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
        />
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-brand-green bg-white shadow-sm"
          style={{ left: `${Math.min(Math.max(scenarioPct, 2), 98)}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] tabular-nums text-brand-muted">
        <span>P10 {formatCr(p10, { bare: true })}</span>
        <span>P50 {formatCr(p50, { bare: true })}</span>
        <span>P90 {formatCr(p90, { bare: true })}</span>
      </div>
    </div>
  );
}

export const DiagnosticValueBridge: React.FC<DiagnosticValueBridgeProps> = ({
  rows,
  totalP50Cr,
  annualRevenueCr,
}) => {
  const [percentilesByLever, setPercentilesByLever] = useState(() =>
    buildDefaultPercentilesByLever(rows),
  );
  const [expandedLevers, setExpandedLevers] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setPercentilesByLever((prev) => mergePercentilesForRows(rows, prev));
  }, [rows]);

  const toggleLeverDetail = (leverId: string) => {
    setExpandedLevers((prev) => {
      const next = new Set(prev);
      if (next.has(leverId)) next.delete(leverId);
      else next.add(leverId);
      return next;
    });
  };

  const { segments, totalScenario } = useMemo(
    () => buildValueBridgeSegments(rows, percentilesByLever, totalP50Cr),
    [rows, percentilesByLever, totalP50Cr],
  );
  const portfolio = useMemo(
    () => buildValueBridgePortfolio(rows, percentilesByLever, totalP50Cr),
    [rows, percentilesByLever, totalP50Cr],
  );
  const concentrationLine = valueBridgeConcentrationLine(portfolio);
  const allAtP50 = useMemo(
    () => segments.every((s) => s.percentile === PERCENTILE_DEFAULT),
    [segments],
  );
  const revenuePct =
    annualRevenueCr && annualRevenueCr > 0
      ? ((totalScenario / annualRevenueCr) * 100).toLocaleString('en-IN', {
          maximumFractionDigits: 1,
          minimumFractionDigits: 0,
        })
      : null;

  const handleLeverPercentile = (leverId: string, value: number) => {
    setPercentilesByLever((prev) => ({ ...prev, [leverId]: value }));
  };

  if (!segments.length) {
    return (
      <p className="text-sm text-brand-muted py-4">No value-at-table levers to display.</p>
    );
  }

  return (
    <section aria-label="Value at table bridge" className="mb-4 space-y-5">
      <p className="text-sm text-brand-muted leading-relaxed">
        Each lever has its own uncertainty slider (P10 conservative → P90 stretch, default P50).
        Portfolio totals reflect your per-lever choices.
      </p>

      <div className="rounded-lg border border-brand-border bg-brand-surface-muted/30 p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
              Portfolio value
            </p>
            <p className="text-2xl font-bold tabular-nums text-brand-ink mt-1">
              {formatCr(totalScenario)}
              <span className="text-sm font-normal text-brand-muted"> /yr</span>
            </p>
            <p className="text-xs text-brand-muted mt-1">
              {allAtP50 ? 'All levers at expected (P50)' : 'Custom per-lever scenarios'}
            </p>
            {revenuePct && (
              <p className="text-xs text-brand-muted mt-0.5">{revenuePct}% of annual revenue</p>
            )}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
              Savings range (P10–P90)
            </p>
            <p className="text-lg font-semibold tabular-nums text-brand-ink mt-1">
              {formatCr(portfolio.totalP10, { bare: true })}
              <span className="text-brand-muted font-normal mx-1">→</span>
              {formatCr(portfolio.totalP90, { bare: true })}
            </p>
            <p className="text-xs text-brand-muted mt-1">
              {formatBandRange(portfolio.totalP10, portfolio.totalP90)} Cr/yr band
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
              Levers in view
            </p>
            <p className="text-lg font-semibold tabular-nums text-brand-ink mt-1">
              {portfolio.leverCount}
            </p>
            {concentrationLine && (
              <p className="text-xs text-brand-muted mt-1 leading-snug">{concentrationLine}</p>
            )}
          </div>
          <div className="sm:col-span-2 lg:col-span-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-2">
              Composition (scenario share)
            </p>
            <div
              className="flex h-8 w-full overflow-hidden rounded-md border border-brand-border bg-white"
              role="img"
              aria-label={`Value bridge of ${segments.length} levers totalling ${formatCr(totalScenario)}`}
            >
              {segments.map((segment) => (
                <div
                  key={segment.leverId}
                  className="h-full min-w-[2px] transition-opacity hover:opacity-90"
                  style={{
                    width: `${Math.max(segment.sharePct, segment.sharePct > 0 ? 0.8 : 0)}%`,
                    backgroundColor: segment.color,
                  }}
                  title={`${segment.leverName}: ${formatCr(segment.scenarioCr, { perYear: true })} (${segment.sharePct.toFixed(1)}%)`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto executive-shell">
        <table className="w-full">
          <thead>
            <tr>
              <th scope="col" className={`${TH_CLASS} w-10`}>
                #
              </th>
              <th scope="col" className={TH_CLASS}>
                Lever
              </th>
              <th scope="col" className={TH_CLASS}>
                Valuation basis
              </th>
              <th scope="col" className={`${TH_CLASS} min-w-[180px]`}>
                Uncertainty (per lever)
              </th>
              <th scope="col" className={`${TH_CLASS} text-right`}>
                Value
              </th>
              <th scope="col" className={`${TH_CLASS} text-right w-16`}>
                Share
              </th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment, index) => {
              const howValued = valueBridgeHowValued(segment);
              const row = segment.row;
              const rationale = valueAtTableRationale(row);
              const calculation = valueAtTableCalculationNote(row);
              const d = row.value_derivation;
              const hasExpandDetail =
                !!rationale ||
                !!calculation ||
                !!d?.calculation_p10 ||
                !!d?.calculation_p90 ||
                !!d?.base_spend_note;
              const expandSummary = hasExpandDetail ? 'Rationale & band detail' : null;
              const isExpanded = expandedLevers.has(segment.leverId);
              const detailId = `lever-detail-${segment.leverId}`;

              return (
                <React.Fragment key={segment.leverId}>
                  <tr
                    className={`border-b border-brand-border ${index < 3 ? 'bg-brand-surface-muted/50' : ''} ${isExpanded ? 'border-b-0' : ''}`}
                  >
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-brand-muted text-xs`}>
                      {String(index + 1).padStart(2, '0')}
                    </td>
                    <td className={`${TD_CLASS} max-w-xs`}>
                      <div className="flex items-start gap-2">
                        <span
                          className="mt-1.5 w-2.5 h-2.5 rounded-sm shrink-0"
                          style={{ backgroundColor: segment.color }}
                          aria-hidden
                        />
                        <div className="min-w-0">
                          <p className="font-medium text-brand-ink leading-snug">{segment.leverName}</p>
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            <ComplexityBadge tier={segment.complexityTier} />
                            {segment.savingsTypeLabel && (
                              <span className="inline-flex items-center rounded-full border border-brand-border bg-white px-2 py-0.5 text-[10px] font-medium text-brand-muted">
                                {segment.savingsTypeLabel}
                              </span>
                            )}
                          </div>
                          {hasExpandDetail && expandSummary && (
                            <button
                              type="button"
                              aria-expanded={isExpanded}
                              aria-controls={detailId}
                              onClick={() => toggleLeverDetail(segment.leverId)}
                              className="group mt-2 flex items-center gap-1.5 text-left text-sm text-brand-navy hover:text-brand-green"
                            >
                              <span
                                aria-hidden
                                className="text-brand-muted transition-transform duration-200 group-hover:text-brand-ink"
                                style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                              >
                                ▸
                              </span>
                              {expandSummary}
                            </button>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className={`${TD_CLASS} max-w-sm`}>
                      {howValued ? (
                        <p className="text-sm text-brand-muted leading-relaxed">{howValued}</p>
                      ) : (
                        <span className="text-brand-muted">—</span>
                      )}
                    </td>
                    <td className={TD_CLASS}>
                      <LeverUncertaintyControl
                        leverName={segment.leverName}
                        p10={segment.p10Cr}
                        p90={segment.p90Cr}
                        percentile={segment.percentile}
                        scenarioCr={segment.scenarioCr}
                        onChange={(value) => handleLeverPercentile(segment.leverId, value)}
                      />
                    </td>
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-right font-semibold`}>
                      {formatCr(segment.scenarioCr, { bare: true })}
                    </td>
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-right text-brand-muted`}>
                      {segment.sharePct.toFixed(0)}%
                    </td>
                  </tr>
                  {isExpanded && hasExpandDetail && (
                    <tr className={`border-b border-brand-border ${index < 3 ? 'bg-brand-surface-muted/50' : ''}`}>
                      <td colSpan={TABLE_COLS} className="px-4 pb-4 pt-1" id={detailId}>
                        <div className="rounded-md border border-brand-border/70 bg-white/80 p-4">
                          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                            {rationale && <DetailBlock label="Why selected" text={rationale} />}
                            {calculation && <DetailBlock label="Calculation" text={calculation} />}
                            {d?.calculation_p10 && d.calculation_p10 !== d.calculation_p50 && (
                              <DetailBlock label="Conservative (P10)" text={d.calculation_p10} />
                            )}
                            {d?.calculation_p90 && d.calculation_p90 !== d.calculation_p50 && (
                              <DetailBlock label="Stretch (P90)" text={d.calculation_p90} />
                            )}
                            {d?.base_spend_note && (
                              <DetailBlock label="Spend pool note" text={d.base_spend_note} />
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-brand-border bg-brand-surface-muted/60">
              <td className={`${TD_CLASS} font-semibold`} colSpan={3}>
                Portfolio total
              </td>
              <td className={TD_CLASS}>
                <PortfolioBandSummary
                  p10={portfolio.totalP10}
                  p50={portfolio.totalP50}
                  p90={portfolio.totalP90}
                  scenarioCr={portfolio.totalScenario}
                />
              </td>
              <td className={`${TD_CLASS} ${NUM_CLASS} text-right font-bold`}>
                {formatCr(totalScenario, { bare: true })}
              </td>
              <td className={`${TD_CLASS} ${NUM_CLASS} text-right text-brand-muted`}>100%</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs text-brand-muted">
        All figures in ₹ Cr/yr. Expand a lever row for rationale and band calculations.
      </p>
    </section>
  );
};
