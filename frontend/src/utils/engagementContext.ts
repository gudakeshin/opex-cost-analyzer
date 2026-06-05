import type { EngagementMeta, SessionManifest } from '../types';

const PLACEHOLDER_INDUSTRY = 'manufacturing_diversified';

/** Industry used for analysis: explicit session/manifest choice beats auto-detected. */
export function effectiveAnalysisIndustry(
  manifest?: SessionManifest | null,
  engagement?: Pick<EngagementMeta, 'industry' | 'detected_industry'>,
): string {
  const manifestIndustry = (manifest?.industry || '').trim();
  if (manifestIndustry) return manifestIndustry;
  const detected = (engagement?.detected_industry || '').trim();
  if (detected) return detected;
  return (engagement?.industry || '').trim();
}

/** Industry for Diagnostic form when engagement still carries the placeholder default. */
export function effectiveEngagementIndustry(
  engagement?: Pick<EngagementMeta, 'industry' | 'detected_industry'>,
): string {
  const userIndustry = (engagement?.industry || '').trim();
  const detected = (engagement?.detected_industry || '').trim();
  if (detected && (!userIndustry || userIndustry === PLACEHOLDER_INDUSTRY)) {
    return detected;
  }
  return userIndustry || detected;
}

export function isPlaceholderIndustry(industry?: string | null): boolean {
  const v = (industry || '').trim();
  return !v || v === PLACEHOLDER_INDUSTRY;
}
