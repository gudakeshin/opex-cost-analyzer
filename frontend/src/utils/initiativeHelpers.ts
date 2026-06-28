import type { Initiative, PercentileBand } from '../types';
import { toCr } from './formatInr';

export const GATE2_AQS_THRESHOLD = 0.65;
export const GATE2_COMMIT_THRESHOLD_PCT = 60;
export const DEFAULT_NPV_DISCOUNT_RATE = 0.1;
export const CTA_Y2_FRACTION = 0.25;

export function getAqs(initiative: Initiative): number | undefined {
  const raw = initiative.aqs ?? initiative.assumption_quality_score;
  if (raw == null) return undefined;
  return Number(raw);
}

/** True when a numeric savings field carries a positive modeled value. */
function isPositiveSavings(v: unknown): boolean {
  if (v == null) return false;
  const n = Number(v);
  return Number.isFinite(n) && n > 0;
}

/** True when the initiative has an explicit or derivable value for this band (no synthetic spread). */
export function hasBandSavings(initiative: Initiative, band: PercentileBand): boolean {
  const key = `${band}_savings` as keyof Initiative;
  const direct = initiative[key];
  if (isPositiveSavings(direct)) return true;
  if (band === 'p50') {
    return [initiative.p50_savings, initiative.gross_savings_y1, initiative.net_npv].some(isPositiveSavings);
  }
  return false;
}

export function getBandSavings(initiative: Initiative, band: PercentileBand): number {
  const key = `${band}_savings` as keyof Initiative;
  const direct = initiative[key];
  if (isPositiveSavings(direct)) return Number(direct);
  if (band === 'p50') {
    for (const v of [initiative.p50_savings, initiative.gross_savings_y1, initiative.net_npv]) {
      if (isPositiveSavings(v)) return Number(v);
    }
  }
  return 0;
}

/** 3-year NPV at the selected percentile band (phased net savings @ 10% WACC). */
export function getBandNpv(
  initiative: Initiative,
  band: PercentileBand,
  discountRate = DEFAULT_NPV_DISCOUNT_RATE,
): number {
  const p50 = getBandSavings(initiative, 'p50');
  const bandSavings = getBandSavings(initiative, band);
  if (p50 <= 0) return Number(initiative.net_npv ?? 0);

  const factor = bandSavings / p50;
  const y1 = Number(initiative.gross_savings_y1 ?? 0) * factor;
  const y2 = Number(initiative.gross_savings_y2 ?? 0) * factor;
  const y3 = Number(initiative.gross_savings_y3 ?? 0) * factor;
  const grossTotal = y1 + y2 + y3;

  if (grossTotal > 0) {
    const ctaTotal = Number(initiative.cost_to_achieve ?? 0) * factor;
    const ctaY1 = ctaTotal * (1 - CTA_Y2_FRACTION);
    const ctaY2 = ctaTotal * CTA_Y2_FRACTION;
    const ny1 = y1 - ctaY1;
    const ny2 = y2 - ctaY2;
    const ny3 = y3;
    const r = discountRate;
    return ny1 / (1 + r) ** 1 + ny2 / (1 + r) ** 2 + ny3 / (1 + r) ** 3;
  }

  const stored = Number(initiative.net_npv ?? 0);
  return stored > 0 ? stored * factor : 0;
}

export function canAcceptInitiative(initiative: Initiative): boolean {
  const aqs = getAqs(initiative);
  if (aqs == null) return true;
  return aqs >= GATE2_AQS_THRESHOLD;
}

export const PENDING_STAGES = new Set(['identified', 'proposed', 'validated']);

export function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    identified: 'Pending',
    proposed: 'Proposed',
    validated: 'Validated',
    committed: 'Committed',
    in_flight: 'In-flight',
    realized: 'Realized',
    rejected: 'Rejected',
    deferred: 'Deferred',
  };
  return map[stage] ?? stage.replace(/_/g, ' ');
}

export function isNeedsActionInitiative(initiative: {
  stage?: string;
  aqs?: number;
  assumption_quality_score?: number;
}): boolean {
  const stage = initiative.stage ?? '';
  if (!PENDING_STAGES.has(stage)) return false;
  const aqs = getAqs(initiative as Initiative);
  if (aqs != null && aqs < GATE2_AQS_THRESHOLD) return true;
  return stage === 'identified' || stage === 'proposed';
}

export function actionReason(initiative: Initiative): { txt: string; tone: 'block' | 'pass' | 'go' } {
  const aqs = getAqs(initiative);
  if (aqs != null && aqs < GATE2_AQS_THRESHOLD) {
    return { txt: 'AQS below Gate 2 — needs evidence', tone: 'block' };
  }
  if (initiative.stage === 'identified') {
    return { txt: 'Unowned — needs validation', tone: 'pass' };
  }
  if (initiative.stage === 'proposed') {
    return { txt: 'Awaiting business case', tone: 'pass' };
  }
  return { txt: 'Ready to commit', tone: 'go' };
}

export function priorityScore(initiative: Initiative): number {
  const p50 = getBandSavings(initiative, 'p50');
  const aqs = getAqs(initiative);
  const gap =
    aqs != null && aqs < GATE2_AQS_THRESHOLD ? 1.6 : initiative.stage === 'identified' ? 1.3 : 1.0;
  return p50 * gap;
}

export function scenarioFactor(scenario: string): number {
  const factors: Record<string, number> = {
    base: 1,
    conservative: 0.75,
    accelerated: 1.05,
    inr_depreciation: 0.87,
    wage_shock: 0.92,
    commodity: 0.9,
    exec_slip: 0.7,
    delayed: 0.85,
    partial_success: 0.65,
    bounce_back: 0.75,
    regulatory_headwind: 0.82,
    volume_growth: 1.08,
  };
  return factors[scenario] ?? 1;
}

/** Derive portfolio scaling from backend sensitivity scenarios when available. */
export function scenarioFactorFromSensitivity(
  scenario: string,
  sensitivity: { scenarios?: Array<{ name?: string; savings_3yr?: number }>; baseline_mid_savings?: number } | null,
): number {
  if (!sensitivity?.scenarios?.length) return scenarioFactor(scenario);
  const baseMid =
    sensitivity.baseline_mid_savings ??
    sensitivity.scenarios.find((s) => s.name === 'base')?.savings_3yr;
  if (!baseMid || baseMid <= 0) return scenarioFactor(scenario);
  const match = sensitivity.scenarios.find((s) => s.name === scenario);
  if (match?.savings_3yr != null && match.savings_3yr > 0) {
    return match.savings_3yr / baseMid;
  }
  return scenarioFactor(scenario);
}

export function valForBand(
  initiative: Initiative,
  band: PercentileBand,
  factor = 1,
): number | null {
  if (!hasBandSavings(initiative, band)) return null;
  return Math.round(getBandSavings(initiative, band) * factor);
}

export function formatBandDisplay(
  initiative: Initiative,
  band: PercentileBand,
  factor: number,
  currency: string,
): string {
  const v = valForBand(initiative, band, factor);
  if (v == null) return '—';
  return toCr(v, currency).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

export function addressabilityScores(initiative: Initiative): {
  regulatory: number;
  contract: number;
  switching: number;
  behaviour: number;
} {
  const addr = initiative.addressability as Record<string, number> | undefined;
  return {
    regulatory: addr?.regulatory ?? initiative.regulatory_override ?? 1,
    contract: addr?.contract ?? initiative.contract_window ?? 0.7,
    switching: addr?.switching ?? initiative.switching_cost ?? 0.8,
    behaviour: addr?.behaviour ?? initiative.cost_behaviour ?? 0.75,
  };
}
