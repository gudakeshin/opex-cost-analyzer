import type { ConflictSummary, Initiative } from '../types';
import { GATE2_AQS_THRESHOLD, getAqs } from './initiativeHelpers';

export type ExceptionAction = 'conflicts' | 'portfolio';

export interface ExceptionItem {
  id: string;
  severity: 'critical' | 'high' | 'medium';
  title: string;
  detail: string;
  href?: string;
  action?: ExceptionAction;
  actionLabel?: string;
}

const PENDING_STAGES = new Set(['identified', 'proposed', 'validated']);

export function isExceptionInitiative(init: Initiative): boolean {
  const stage = init.stage ?? '';
  if (!PENDING_STAGES.has(stage)) return false;
  const aqs = getAqs(init);
  if (aqs != null && aqs < GATE2_AQS_THRESHOLD) return true;
  return stage === 'identified' || stage === 'proposed';
}

export function countInitiativeExceptions(initiatives: Initiative[]): number {
  return initiatives.filter(isExceptionInitiative).length;
}

export function buildInitiativeExceptionItems(initiatives: Initiative[]): ExceptionItem[] {
  return initiatives
    .filter(isExceptionInitiative)
    .map((init) => {
      const aqs = getAqs(init);
      const lowAqs = aqs != null && aqs < GATE2_AQS_THRESHOLD;
      return {
        id: init.initiative_id,
        severity: lowAqs ? 'high' : 'medium',
        title: init.lever || init.category || init.initiative_id,
        detail: lowAqs
          ? `AQS ${aqs!.toFixed(2)} below gate (${GATE2_AQS_THRESHOLD}) — review before accept`
          : `Stage: ${init.stage} — pending decision`,
        action: 'portfolio',
        actionLabel: 'Review',
      };
    });
}

export function buildConflictExceptionItems(summary: ConflictSummary | null): ExceptionItem[] {
  if (!summary || !summary.unresolved) return [];
  const items: ExceptionItem[] = [];
  const total = summary.unresolved ?? 0;
  if (total > 0) {
    items.push({
      id: 'conflicts-unresolved',
      severity: (summary.by_severity?.critical ?? 0) > 0 ? 'critical' : 'high',
      title: `${total} unresolved data conflict${total === 1 ? '' : 's'}`,
      detail: 'Cross-source mismatches detected — review each recommendation before applying.',
      action: 'conflicts',
      actionLabel: 'Resolve',
    });
  }
  return items;
}

export function mergeExceptionItems(...groups: ExceptionItem[][]): ExceptionItem[] {
  const seen = new Set<string>();
  const out: ExceptionItem[] = [];
  for (const group of groups) {
    for (const item of group) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      out.push(item);
    }
  }
  return out.sort((a, b) => {
    const rank = { critical: 0, high: 1, medium: 2 };
    return rank[a.severity] - rank[b.severity];
  });
}
