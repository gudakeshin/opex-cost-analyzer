import type {
  PackEditorDraft,
  PackEditorTabId,
  SectorPackDetailResponse,
  SectorPackRow,
} from '../types/sectorPack';
import { draftToJson, parseDetailToDraft } from './sectorPackEditors';

export const EDITOR_TABS: PackEditorTabId[] = [
  'taxonomy',
  'peers',
  'levers',
  'kpis',
  'benchmarks',
  'sources',
];

export type ManifestFormState = Record<
  'sector' | 'status' | 'description' | 'effective_from' | 'reporting_currency' | 'fiscal_year_end',
  string
>;

export function buildManifestForm(
  detail: SectorPackDetailResponse,
  selectedPack?: SectorPackRow,
): ManifestFormState {
  const m = (detail.manifest ?? {}) as Record<string, unknown>;
  return {
    sector: String(m.sector ?? detail.sector ?? ''),
    status: String(m.status ?? selectedPack?.status ?? 'scaffold'),
    description: String(m.description ?? ''),
    effective_from: String(m.effective_from ?? ''),
    reporting_currency: String(m.reporting_currency ?? 'INR'),
    fiscal_year_end: String(m.fiscal_year_end ?? 'March 31'),
  };
}

export function hydrateEditorDrafts(detail: SectorPackDetailResponse): {
  drafts: Record<PackEditorTabId, PackEditorDraft>;
  jsonText: Record<PackEditorTabId, string>;
} {
  const drafts = Object.fromEntries(
    EDITOR_TABS.map((t) => [t, parseDetailToDraft(t, detail)]),
  ) as Record<PackEditorTabId, PackEditorDraft>;
  const jsonText = Object.fromEntries(
    EDITOR_TABS.map((t) => [t, draftToJson(drafts[t])]),
  ) as Record<PackEditorTabId, string>;
  return { drafts, jsonText };
}
