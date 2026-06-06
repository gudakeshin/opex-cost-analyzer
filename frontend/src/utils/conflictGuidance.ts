import type { DataConflict } from '../types';

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'border-l-red-500 bg-red-50/40',
  high: 'border-l-amber-500 bg-amber-50/40',
  medium: 'border-l-brand-navy bg-brand-surface-muted/50',
  low: 'border-l-gray-300 bg-gray-50/40',
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  high: 'bg-amber-100 text-amber-900',
  medium: 'bg-slate-100 text-slate-700',
  low: 'bg-gray-100 text-gray-600',
};

export function conflictSeverityStyle(severity?: string): string {
  return SEVERITY_STYLES[severity ?? 'medium'] ?? SEVERITY_STYLES.medium;
}

export function conflictSeverityBadge(severity?: string): string {
  return SEVERITY_BADGE[severity ?? 'medium'] ?? SEVERITY_BADGE.medium;
}

/** Fallback labels when API enrichment is missing (older cached responses). */
export function fallbackConflictTitle(conflict: DataConflict): string {
  const type = String(conflict.conflict_type ?? 'conflict');
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export function fallbackConflictDescription(conflict: DataConflict): string {
  const srcA = conflict.source_a ?? 'source A';
  const srcB = conflict.source_b ?? 'source B';
  const parts = [`${srcA} vs ${srcB}`];
  if (conflict.amount_a != null && conflict.amount_b != null) {
    parts.push(`amounts ${conflict.amount_a} vs ${conflict.amount_b}`);
  }
  if (conflict.delta_pct != null) {
    parts.push(`${conflict.delta_pct}% difference`);
  }
  return parts.join(' · ');
}

export function fallbackRecommendation(conflict: DataConflict): string {
  if (conflict.requires_manual_review || conflict.resolution_strategy === 'escalate') {
    return 'Review with Finance and confirm which source should drive savings before committing numbers.';
  }
  return 'Apply the recommended reconciliation so cross-source spend aligns before pipeline commit.';
}
