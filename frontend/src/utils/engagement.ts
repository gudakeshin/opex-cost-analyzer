const PLACEHOLDER_NAMES = new Set([
  'opex engagement',
  'new engagement',
  'unnamed engagement',
  'client',
  '',
]);

export function isPlaceholderCompanyName(name?: string | null): boolean {
  if (!name?.trim()) return true;
  return PLACEHOLDER_NAMES.has(name.trim().toLowerCase());
}

export function isClientEngagementReady(
  hasAnalysis: boolean,
  companyName?: string | null,
): boolean {
  return hasAnalysis && !isPlaceholderCompanyName(companyName);
}
