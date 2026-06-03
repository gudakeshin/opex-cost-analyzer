/** Spend taxonomy display names — mirrors skills/spend-profiler/references/spend_taxonomy.json */
const CATEGORY_LABELS: Record<string, string> = {
  IT: 'IT & Technology',
  PROF_SVCS: 'Professional Services',
  FACILITIES: 'Facilities & Real Estate',
  TRAVEL: 'Travel & Entertainment',
  MARKETING: 'Marketing & Advertising',
  HR: 'HR & Recruitment',
  LOGISTICS: 'Logistics & Supply Chain',
  TELECOM: 'Telecommunications',
  INSURANCE: 'Insurance & Risk',
  OFFICE: 'Office Supplies & Equipment',
  OUTSOURCED: 'Outsourced Operations',
  RND: 'R&D & Engineering',
  FIN_SVCS: 'Financial Services',
  CONTINGENT: 'Contingent Workforce',
  OTHER: 'Other / Unclassified',
  POWER_ENERGY: 'Power & Energy',
  RELATED_PARTY: 'Related-Party & Intercompany',
};

const AUTO_GENERATED_NAME = /^(Rnd|It|Hr|Prof Svcs|Related Party|Contingent|Outsourced)$/i;

export function resolveCategoryLabel(
  categoryId?: string,
  categoryName?: string,
): string {
  const id = (categoryId ?? '').trim();
  const name = (categoryName ?? '').trim();

  if (name && !AUTO_GENERATED_NAME.test(name)) {
    return name;
  }
  if (id && CATEGORY_LABELS[id]) {
    return CATEGORY_LABELS[id];
  }
  if (name) {
    return name;
  }
  if (id) {
    return id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return 'Unknown';
}

export function gapHeadroomCr(gap: Record<string, unknown>): number {
  const raw =
    gap.benchmark_p50_to_p25_band_cr ??
    gap.gap_cr ??
    gap.headroom_to_p25_cr ??
    0;
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}
