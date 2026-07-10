import type { AuditLogEntry, ManifestFileEntry, SessionManifest, V1ChatResponse } from '../types';

export type ProvenanceSource = {
  label: string;
  detail?: string;
  kind?: 'fact' | 'inference';
};

export type RunProvenance = {
  sources: ProvenanceSource[];
  narrativeTag: Record<string, unknown> | null;
  localAudit: AuditLogEntry[];
};

const HANDLED_ADVISORY_KEYS = new Set([
  'executive_takeaway',
  'sme_qualification_narrative',
  'category_focus_section',
  'quick_wins_from_data',
  'executive_callouts',
  'business_levers',
  'priority_actions_30_60_90',
  'recommendations',
  'citations',
]);

export const ADVISORY_HANDLED_KEYS = HANDLED_ADVISORY_KEYS;

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function citationSources(advisory: Record<string, unknown> | undefined): ProvenanceSource[] {
  const cites = Array.isArray(advisory?.citations) ? advisory!.citations : [];
  return cites
    .map((c) => {
      const row = asRecord(c);
      if (!row) return null;
      const skill = String(row.source_skill ?? 'skill');
      const metric = String(row.metric ?? '');
      const value = String(row.value ?? '');
      const rows = row.row_count != null ? ` · ${row.row_count} rows` : '';
      const vintage = row.vintage ? ` · vintage ${row.vintage}` : '';
      const sample = row.sample_n ? ` · n=${row.sample_n}` : '';
      return {
        label: `[${skill}] ${metric}`,
        detail: `${value}${rows}${vintage}${sample}`.trim(),
        kind: 'fact' as const,
      };
    })
    .filter(Boolean) as ProvenanceSource[];
}

function fallbackReasonSources(reasons: Record<string, unknown> | undefined): ProvenanceSource[] {
  if (!reasons) return [];
  return Object.entries(reasons)
    .filter(([, v]) => v != null && String(v).trim() !== '')
    .map(([key, val]) => ({
      label: `Fallback: ${key.replace(/_/g, ' ')}`,
      detail: String(val).replace(/_/g, ' '),
      kind: 'inference' as const,
    }));
}

function manifestFileSources(manifest: SessionManifest | null | undefined): ProvenanceSource[] {
  const files = (manifest?.files ?? []) as ManifestFileEntry[];
  return files.map((f) => ({
    label: f.name || 'Uploaded file',
    detail: f.content_type ? `${f.content_type}${f.size_bytes ? ` · ${f.size_bytes} bytes` : ''}` : 'Session upload',
    kind: 'fact' as const,
  }));
}

export function deriveRunProvenance(params: {
  chat?: V1ChatResponse | null;
  manifest?: SessionManifest | null;
  runId?: string;
}): RunProvenance {
  const { chat, manifest, runId } = params;
  const advisory = asRecord(chat?.advisory_sections) ?? undefined;
  const sources: ProvenanceSource[] = [];

  sources.push(...manifestFileSources(manifest));
  sources.push(...citationSources(advisory));

  const narrativeMode = String(chat?.response_metadata?.narrative_mode ?? '').trim();
  const usedLlm = chat?.used_llm_synthesis;
  if (narrativeMode === 'deterministic' || usedLlm === false) {
    sources.push({
      label: 'Deterministic composer',
      detail: 'Narrative composed from skill outputs without LLM synthesis',
      kind: 'fact',
    });
  } else if (usedLlm === true || narrativeMode === 'llm') {
    sources.push({
      label: 'LLM synthesis',
      detail: 'Model-assisted narrative from validated skill outputs',
      kind: 'inference',
    });
  }

  sources.push(...fallbackReasonSources(chat?.fallback_reasons as Record<string, unknown> | undefined));

  const narrativeTag: Record<string, unknown> = {};
  if (narrativeMode) narrativeTag.narrative_mode = narrativeMode;
  if (chat?.narrative_provenance_tag) {
    Object.assign(narrativeTag, chat.narrative_provenance_tag);
  }
  const skip = String(chat?.fallback_reasons?.llm_advisory ?? chat?.fallback_reasons?.chat_synthesis ?? '').trim();
  if (skip) narrativeTag.llm_skip_reason = skip;
  if (chat?.degraded_mode) narrativeTag.degraded_mode = true;

  const ts = new Date().toISOString();
  const localAudit: AuditLogEntry[] = [];
  if (runId) {
    localAudit.push({
      ts,
      message: `Analysis run ${runId.slice(0, 8)}… — provenance refreshed (${sources.length} sources)`,
    });
  }

  return {
    sources: sources.length > 0 ? sources : [],
    narrativeTag: Object.keys(narrativeTag).length > 0 ? narrativeTag : null,
    localAudit,
  };
}

export function deriveProvenanceFromSession(params: {
  manifest?: SessionManifest | null;
  advisorySections?: Record<string, unknown>;
  runId?: string;
}): RunProvenance {
  return deriveRunProvenance({
    chat: {
      response_text: '',
      advisory_sections: params.advisorySections,
      used_llm_synthesis: false,
      response_metadata: { narrative_mode: 'deterministic' },
    },
    manifest: params.manifest,
    runId: params.runId,
  });
}

/** Months since ISO or YYYY-Qn vintage string; null if unparseable. */
export function benchmarkVintageAgeMonths(vintage: string | undefined): number | null {
  if (!vintage) return null;
  const iso = Date.parse(vintage);
  if (!Number.isNaN(iso)) {
    return Math.floor((Date.now() - iso) / (30.44 * 24 * 3600 * 1000));
  }
  const q = vintage.match(/^(\d{4})-Q([1-4])$/i);
  if (q) {
    const month = (parseInt(q[2], 10) - 1) * 3 + 2;
    const d = new Date(parseInt(q[1], 10), month, 15);
    return Math.floor((Date.now() - d.getTime()) / (30.44 * 24 * 3600 * 1000));
  }
  return null;
}

export function benchmarkVintageWarning(vintage: string | undefined, sampleN?: number): string | null {
  const warnings: string[] = [];
  const age = benchmarkVintageAgeMonths(vintage);
  if (age != null && age > 18) warnings.push(`benchmark ${age}mo old`);
  if (sampleN != null && sampleN > 0 && sampleN < 5) warnings.push(`n=${sampleN} peers`);
  return warnings.length > 0 ? warnings.join(' · ') : null;
}
