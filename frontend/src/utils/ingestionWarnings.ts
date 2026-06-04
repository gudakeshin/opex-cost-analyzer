import type { SessionManifest, SessionResponse } from '../types';

export interface IngestionQuality {
  rows_parsed?: number;
  rows_with_amount?: number;
  total_amount?: number;
  zero_spend_warning?: boolean;
  column_mapping_note?: string;
}

export interface IngestionReportWithQuality {
  source_file?: string;
  sheets_ingested?: Array<{ sheet?: string; rows?: number; strategy?: string }>;
  warnings?: string[];
  quality?: IngestionQuality;
  layout?: string;
  files?: IngestionReportWithQuality[];
}

function primaryReport(manifest: SessionManifest | null | undefined): IngestionReportWithQuality | null {
  const report = manifest?.ingestion_report as IngestionReportWithQuality | undefined;
  if (!report) return null;
  if (report.files?.length) return report.files[0] ?? null;
  return report;
}

export function ingestionQualityFromManifest(
  manifest: SessionManifest | null | undefined,
): IngestionQuality | null {
  return primaryReport(manifest)?.quality ?? null;
}

export function ingestionWarningsFromManifest(
  manifest: SessionManifest | null | undefined,
): string[] {
  const report = primaryReport(manifest);
  if (!report) return [];
  const out: string[] = [];
  if (report.warnings?.length) out.push(...report.warnings);
  if (report.quality?.column_mapping_note) out.push(report.quality.column_mapping_note);
  return out;
}

export function showZeroSpendIngestionWarning(
  manifest: SessionManifest | null | undefined,
  analysis: SessionResponse | null,
): boolean {
  const quality = ingestionQualityFromManifest(manifest);
  if (quality?.zero_spend_warning) return true;
  const ingested = primaryReport(manifest)?.sheets_ingested ?? [];
  const parsedRows = ingested.reduce((n, s) => n + (s.rows ?? 0), 0);
  if (parsedRows <= 0) return false;
  const totalSpend = Number(
    (analysis?.skill_outputs as Record<string, unknown> | undefined)?.['spend-profiler'] &&
      (
        (analysis?.skill_outputs as Record<string, unknown>)['spend-profiler'] as Record<
          string,
          unknown
        >
      ).total_spend,
  );
  return !Number.isFinite(totalSpend) || totalSpend <= 0;
}
