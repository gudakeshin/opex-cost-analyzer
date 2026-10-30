import type {
  BenchmarkCategoryDraftRow,
  BenchmarksDraft,
  KpiRow,
  LeverRow,
  LeversDraft,
  PackEditorDraft,
  PackEditorTabId,
  PeersDraft,
  SectorPackDetailResponse,
  SourcesDraft,
  TaxonomyDraft,
} from '../types/sectorPack';

export function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function stripLinkedLevers(categories: Record<string, Record<string, unknown>>): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const [catId, row] of Object.entries(categories)) {
    const { linked_levers: _linked, ...rest } = row;
    out[catId] = rest;
  }
  return out;
}

function categoriesToDraftRows(categories: Record<string, Record<string, unknown>>): BenchmarkCategoryDraftRow[] {
  return Object.entries(categories).map(([category_id, row]) => ({
    category_id,
    P25: row.P25 as number | undefined,
    P50: row.P50 as number | undefined,
    P75: row.P75 as number | undefined,
    P90: row.P90 as number | undefined,
    unit: row.unit as string | undefined,
    confidence: row.confidence as string | undefined,
    source_note: row.source_note as string | undefined,
  }));
}

function draftRowsToCategories(rows: BenchmarkCategoryDraftRow[]): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const row of rows) {
    const { category_id, ...fields } = row;
    if (!category_id?.trim()) continue;
    out[category_id.trim()] = { ...fields };
  }
  return out;
}

function mergeLeversById(existing: LeverRow[], edited: LeverRow[]): LeverRow[] {
  const existingById = new Map(existing.map((lv) => [String(lv.lever_id), lv]));
  const editedIds = new Set<string>();
  const merged: LeverRow[] = [];

  for (const row of edited) {
    const id = String(row.lever_id ?? '').trim();
    if (!id) {
      merged.push(clone(row));
      continue;
    }
    editedIds.add(id);
    const prior = existingById.get(id);
    merged.push(prior ? { ...clone(prior), ...clone(row), lever_id: id } : clone(row));
  }

  for (const [id, row] of existingById) {
    if (!editedIds.has(id)) {
      merged.push(clone(row));
    }
  }

  return merged;
}

export function parseDetailToDraft(tab: PackEditorTabId, detail: SectorPackDetailResponse): PackEditorDraft {
  switch (tab) {
    case 'kpis':
      return clone(detail.kpi_pack ?? []);

    case 'taxonomy': {
      const tax = detail.taxonomy_extension ?? {};
      return {
        base_taxonomy_version: String(tax.base_taxonomy_version ?? '1.0'),
        additional_categories: clone(tax.additional_categories ?? []),
        overrides: clone(tax.overrides ?? []),
      };
    }

    case 'peers': {
      const peerSet = (detail.peer_set ?? {}) as Record<string, unknown>;
      const metrics = (peerSet.benchmark_metrics ?? detail.peer_benchmark_metrics ?? {}) as Record<
        string,
        { p25?: number; p50?: number; p75?: number }
      >;
      return {
        sector: String(peerSet.sector ?? detail.sector ?? detail.pack_id),
        currency: String(peerSet.currency ?? 'INR'),
        data_source: String(peerSet.data_source ?? ''),
        refresh_date: String(peerSet.refresh_date ?? ''),
        peers: clone((peerSet.peers as PeersDraft['peers']) ?? detail.peers ?? []),
        benchmark_metrics: Object.entries(metrics).map(([key, vals]) => ({
          key,
          p25: vals.p25,
          p50: vals.p50,
          p75: vals.p75,
        })),
      };
    }

    case 'levers': {
      const doc = (detail.levers_document ?? {}) as Record<string, unknown>;
      const levers = Array.isArray(doc.levers)
        ? clone(doc.levers as LeverRow[])
        : clone(detail.levers ?? []);
      return {
        sector: String(doc.sector ?? detail.sector ?? detail.pack_id),
        source_type: String(doc.source_type ?? 'studio'),
        source_verification_note: String(doc.source_verification_note ?? ''),
        levers,
      };
    }

    case 'benchmarks': {
      const doc = (detail.benchmarks_document ?? {}) as Record<string, unknown>;
      const packId = detail.pack_id;
      const block = ((doc.benchmarks as Record<string, unknown>)?.[packId] ?? {}) as Record<string, unknown>;
      const categories =
        Object.keys(block.categories ?? {}).length > 0
          ? stripLinkedLevers(block.categories as Record<string, Record<string, unknown>>)
          : stripLinkedLevers((detail.categories ?? {}) as Record<string, Record<string, unknown>>);
      const meta = (doc.source_metadata ?? detail.source_metadata ?? {}) as Record<string, unknown>;
      return {
        sector: String(doc.sector ?? detail.sector ?? packId),
        version: String(doc.version ?? detail.version ?? '0.1'),
        vintage_date: String(doc.vintage_date ?? detail.vintage_date ?? ''),
        confidence_overall: String(doc.confidence_overall ?? detail.confidence_overall ?? ''),
        source_metadata: {
          methodology: String(meta.methodology ?? ''),
          sample_size: meta.sample_size != null ? String(meta.sample_size) : '',
        },
        categories: categoriesToDraftRows(categories),
      };
    }

    case 'sources': {
      const src = detail.benchmark_sources ?? {};
      return {
        source_validation_date: String(src.source_validation_date ?? ''),
        source_validation_note: String(src.source_validation_note ?? ''),
        sector: String(src.sector ?? detail.sector ?? detail.pack_id),
        free_sources: clone(src.free_sources ?? []),
        licensed_sources_stubs: clone(src.licensed_sources_stubs ?? []),
      };
    }

    default:
      throw new Error(`Unknown tab: ${tab}`);
  }
}

export function serializeDraftToPayload(
  tab: PackEditorTabId,
  draft: PackEditorDraft,
  detail: SectorPackDetailResponse,
): unknown {
  const packId = detail.pack_id;

  switch (tab) {
    case 'kpis':
      return clone(draft as KpiRow[]);

    case 'taxonomy': {
      const taxDraft = draft as TaxonomyDraft;
      const existing = (detail.taxonomy_extension ?? {}) as Record<string, unknown>;
      return {
        ...clone(existing),
        base_taxonomy_version: taxDraft.base_taxonomy_version,
        additional_categories: clone(taxDraft.additional_categories),
        overrides: clone(taxDraft.overrides),
      };
    }

    case 'peers': {
      const peersDraft = draft as PeersDraft;
      const existing = (detail.peer_set ?? {}) as Record<string, unknown>;
      const benchmark_metrics: Record<string, { p25?: number; p50?: number; p75?: number }> = {};
      for (const row of peersDraft.benchmark_metrics) {
        const key = row.key.trim();
        if (!key) continue;
        benchmark_metrics[key] = { p25: row.p25, p50: row.p50, p75: row.p75 };
      }
      return {
        ...clone(existing),
        sector: peersDraft.sector,
        currency: peersDraft.currency,
        data_source: peersDraft.data_source || undefined,
        refresh_date: peersDraft.refresh_date || undefined,
        peers: clone(peersDraft.peers),
        benchmark_metrics,
      };
    }

    case 'levers': {
      const leversDraft = draft as LeversDraft;
      const existing = (detail.levers_document ?? {}) as Record<string, unknown>;
      const existingLevers = Array.isArray(existing.levers) ? (existing.levers as LeverRow[]) : (detail.levers ?? []);
      return {
        ...clone(existing),
        sector: leversDraft.sector,
        source_type: leversDraft.source_type,
        source_verification_note: leversDraft.source_verification_note || undefined,
        levers: mergeLeversById(existingLevers, leversDraft.levers),
      };
    }

    case 'benchmarks': {
      const benchDraft = draft as BenchmarksDraft;
      const existing = (detail.benchmarks_document ?? {}) as Record<string, unknown>;
      const existingBlock = ((existing.benchmarks as Record<string, unknown>)?.[packId] ?? {}) as Record<
        string,
        unknown
      >;
      const categories = draftRowsToCategories(benchDraft.categories);
      const sampleSize = benchDraft.source_metadata.sample_size.trim();
      const existingMeta = (existing.source_metadata ?? detail.source_metadata ?? {}) as Record<string, unknown>;
      return {
        ...clone(existing),
        sector: benchDraft.sector,
        version: benchDraft.version,
        vintage_date: benchDraft.vintage_date || undefined,
        confidence_overall: benchDraft.confidence_overall || undefined,
        source_metadata: {
          ...clone(existingMeta),
          methodology: benchDraft.source_metadata.methodology || existingMeta.methodology,
          sample_size: sampleSize ? Number(sampleSize) : existingMeta.sample_size,
        },
        benchmarks: {
          ...(existing.benchmarks as Record<string, unknown> | undefined),
          [packId]: {
            ...clone(existingBlock),
            categories,
          },
        },
      };
    }

    case 'sources': {
      const sourcesDraft = draft as SourcesDraft;
      const existing = (detail.benchmark_sources ?? {}) as Record<string, unknown>;
      return {
        ...clone(existing),
        source_validation_date: sourcesDraft.source_validation_date || undefined,
        source_validation_note: sourcesDraft.source_validation_note || undefined,
        sector: sourcesDraft.sector,
        free_sources: clone(sourcesDraft.free_sources),
        licensed_sources_stubs: clone(sourcesDraft.licensed_sources_stubs),
      };
    }

    default:
      throw new Error(`Unknown tab: ${tab}`);
  }
}

export function draftToJson(draft: PackEditorDraft): string {
  return JSON.stringify(draft, null, 2);
}

export function parseDraftFromJson(tab: PackEditorTabId, text: string): PackEditorDraft {
  const parsed = JSON.parse(text) as PackEditorDraft;
  if (tab === 'kpis' && !Array.isArray(parsed)) {
    throw new Error('KPI draft must be a JSON array');
  }
  return parsed;
}

export function isPackEditorTab(tab: string): tab is PackEditorTabId {
  return ['taxonomy', 'peers', 'levers', 'kpis', 'benchmarks', 'sources'].includes(tab);
}
