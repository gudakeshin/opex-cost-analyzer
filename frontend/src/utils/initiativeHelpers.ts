import type { Initiative, PercentileBand } from '../types';

export const GATE2_AQS_THRESHOLD = 0.65;
export const GATE2_COMMIT_THRESHOLD_PCT = 60;

export function getAqs(initiative: Initiative): number | undefined {
  const raw = initiative.aqs ?? initiative.assumption_quality_score;
  if (raw == null) return undefined;
  return Number(raw);
}

export function getBandSavings(initiative: Initiative, band: PercentileBand): number {
  const key = `${band}_savings` as keyof Initiative;
  const direct = initiative[key];
  if (direct != null && Number.isFinite(Number(direct))) return Number(direct);
  const base = Number(initiative.gross_savings_y1 ?? initiative.net_npv ?? 0);
  if (band === 'p10') return base * 0.7;
  if (band === 'p90') return base * 1.3;
  return base;
}

export function canAcceptInitiative(initiative: Initiative): boolean {
  const aqs = getAqs(initiative);
  if (aqs == null) return true;
  return aqs >= GATE2_AQS_THRESHOLD;
}

export function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    identified: 'Pending',
    proposed: 'Proposed',
    committed: 'Committed',
    in_flight: 'In-flight',
    realized: 'Realized',
    rejected: 'Rejected',
    deferred: 'Deferred',
  };
  return map[stage] ?? stage.replace(/_/g, ' ');
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
