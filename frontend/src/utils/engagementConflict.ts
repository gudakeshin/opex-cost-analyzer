import { sectorLabel } from '../constants/sectors';
import type { SessionManifest } from '../types';

export interface EngagementSanityConflict {
  kind: string;
  severity?: string;
  engagement_company?: string;
  detected_company?: string;
  detected_companies?: string[];
  engagement_industry?: string;
  engagement_industry_label?: string;
  detected_industry?: string;
  detected_industry_label?: string;
  industry_spend?: string | null;
  detected_industries?: string[];
  source?: string;
  signal_source?: string;
  message?: string;
}

export interface EngagementSanity {
  engagement_company?: string | null;
  has_diagnostic_context?: boolean;
  upload_signals?: Array<{ source?: string; file?: string; company_guess?: string }>;
  conflicts?: EngagementSanityConflict[];
  has_conflicts?: boolean;
}

export function engagementSanityFromManifest(
  manifest: SessionManifest | null | undefined,
): EngagementSanity | null {
  const sanity = (manifest as SessionManifest & { engagement_sanity?: EngagementSanity })
    ?.engagement_sanity;
  return sanity ?? null;
}

export function activeEngagementConflicts(
  manifest: SessionManifest | null | undefined,
  sessionId: string | null,
  dismissedKeys: Set<string>,
): EngagementSanityConflict[] {
  const sanity = engagementSanityFromManifest(manifest);
  if (!sanity?.has_conflicts || !sanity.conflicts?.length) return [];
  return sanity.conflicts.filter((c) => {
    const key = conflictDismissKey(sessionId, c);
    return !dismissedKeys.has(key);
  });
}

export function conflictDismissKey(
  sessionId: string | null,
  conflict: EngagementSanityConflict,
): string {
  const sid = sessionId ?? 'none';
  const det =
    conflict.detected_company ??
    conflict.detected_companies?.join('|') ??
    conflict.detected_industry ??
    conflict.detected_industries?.join('|') ??
    '';
  const engagement =
    conflict.engagement_company ?? conflict.engagement_industry ?? '';
  return `${sid}:${conflict.kind}:${engagement}:${det}:${conflict.source ?? conflict.signal_source ?? ''}`;
}

export function primaryDetectedCompany(
  conflicts: EngagementSanityConflict[],
): string | null {
  for (const c of conflicts) {
    if (c.detected_company) return c.detected_company;
  }
  return null;
}

export function primaryDetectedIndustry(
  conflicts: EngagementSanityConflict[],
): string | null {
  const industryConflict = conflicts.find((c) => c.kind === 'industry_mismatch');
  return industryConflict?.detected_industry ?? null;
}

export function primaryDetectedIndustryLabel(
  conflicts: EngagementSanityConflict[],
): string | null {
  const industryConflict = conflicts.find((c) => c.kind === 'industry_mismatch');
  if (!industryConflict) return null;
  return (
    industryConflict.detected_industry_label ??
    sectorLabel(industryConflict.detected_industry)
  );
}

export function engagementIndustryLabel(
  conflicts: EngagementSanityConflict[],
  manifest?: SessionManifest | null,
): string | null {
  const industryConflict = conflicts.find((c) => c.kind === 'industry_mismatch');
  if (industryConflict?.engagement_industry_label) {
    return industryConflict.engagement_industry_label;
  }
  if (industryConflict?.engagement_industry) {
    return sectorLabel(industryConflict.engagement_industry);
  }
  return manifest?.industry ? sectorLabel(manifest.industry) : null;
}

export function conflictSummaryMessage(conflicts: EngagementSanityConflict[]): string {
  if (conflicts.length === 1) {
    return (
      conflicts[0].message?.replace(/\*\*/g, '') ??
      'Uploaded spend may not match the engagement company from Diagnostic.'
    );
  }
  return (
    `${conflicts.length} engagement context issues detected. ` +
    'Review uploaded files before trusting analysis results.'
  );
}
