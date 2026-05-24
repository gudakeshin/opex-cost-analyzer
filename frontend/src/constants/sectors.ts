export const SECTOR_OPTIONS = [
  { value: 'bfsi_banks', label: 'BFSI / Banks' },
  { value: 'conglomerate', label: 'Conglomerate' },
  { value: 'energy_utilities', label: 'Energy & Utilities' },
  { value: 'financial_services_nonbank', label: 'Financial Services (Non-bank)' },
  { value: 'fmcg_consumer', label: 'FMCG / Consumer' },
  { value: 'gcc_capability_centers', label: 'GCC Capability Centers' },
  { value: 'healthcare_hospitals', label: 'Healthcare & Hospitals' },
  { value: 'hospitality_travel', label: 'Hospitality & Travel' },
  { value: 'insurance_general', label: 'Insurance (General)' },
  { value: 'it_ites', label: 'IT / ITES' },
  { value: 'manufacturing_diversified', label: 'Manufacturing (Diversified)' },
  { value: 'pharma_lifesciences', label: 'Pharma & Life Sciences' },
  { value: 'psu_cpse', label: 'PSU / CPSE' },
  { value: 'retail_organized', label: 'Retail (Organized)' },
  { value: 'telecom_infra', label: 'Telecom & Infrastructure' },
] as const;

export function sectorLabel(packId: string | undefined): string {
  if (!packId) return 'Not set';
  return SECTOR_OPTIONS.find((o) => o.value === packId)?.label ?? packId.replace(/_/g, ' ');
}
