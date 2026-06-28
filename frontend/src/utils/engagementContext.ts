import type { EngagementMeta, SessionManifest } from '../types';

const PLACEHOLDER_INDUSTRY = 'manufacturing_diversified';

/** Industry used for analysis: user-set sector beats auto-detected suggestions. */
export function effectiveAnalysisIndustry(
  manifest?: SessionManifest | null,
  engagement?: Pick<EngagementMeta, 'industry' | 'detected_industry' | 'industry_user_set'>,
): string {
  const manifestIndustry = (manifest?.industry || '').trim();
  if (manifestIndustry && !isPlaceholderIndustry(manifestIndustry)) {
    return manifestIndustry;
  }
  const engagementIndustry = (engagement?.industry || '').trim();
  if (engagementIndustry && (engagement?.industry_user_set || !isPlaceholderIndustry(engagementIndustry))) {
    return engagementIndustry;
  }
  const detected = (engagement?.detected_industry || '').trim();
  if (detected) return detected;
  return manifestIndustry || engagementIndustry;
}

/** Industry for Diagnostic form when engagement still carries the placeholder default. */
export function effectiveEngagementIndustry(
  engagement?: Pick<EngagementMeta, 'industry' | 'detected_industry' | 'industry_user_set'>,
): string {
  const userIndustry = (engagement?.industry || '').trim();
  const detected = (engagement?.detected_industry || '').trim();
  if (
    detected &&
    !engagement?.industry_user_set &&
    (!userIndustry || userIndustry === PLACEHOLDER_INDUSTRY)
  ) {
    return detected;
  }
  return userIndustry || detected;
}

export function isPlaceholderIndustry(industry?: string | null): boolean {
  const v = (industry || '').trim();
  return !v || v === PLACEHOLDER_INDUSTRY;
}
