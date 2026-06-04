import React from 'react';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { sectorLabel } from '../../../constants/sectors';

interface SheetGraphNode {
  sheet_name?: string;
  role?: string;
}

interface IngestedSheet {
  sheet?: string;
  rows?: number;
  strategy?: string;
}

interface SkippedSheet {
  sheet?: string;
  role?: string;
  reason?: string;
}

interface IngestionQuality {
  rows_parsed?: number;
  rows_with_amount?: number;
  total_amount?: number;
  zero_spend_warning?: boolean;
  column_mapping_note?: string;
}

interface IngestionReport {
  source_file?: string;
  sheets_ingested?: IngestedSheet[];
  sheets_skipped?: SkippedSheet[];
  warnings?: string[];
  quality?: IngestionQuality;
  layout?: string;
  files?: IngestionReport[];
}

interface ModelManifest {
  confidence?: number;
  ingestion_strategy?: string;
  ingestion_notes?: string;
  sheet_graph?: SheetGraphNode[];
  model_type?: string;
}

interface WorkbookIngestionPanelProps {
  modelManifest?: ModelManifest | null;
  ingestionReport?: IngestionReport | null;
  industry?: string;
  lineCount?: number;
}

function normalizeReports(report: IngestionReport | null | undefined): IngestionReport[] {
  if (!report) return [];
  if (report.files?.length) return report.files;
  return [report];
}

export const WorkbookIngestionPanel: React.FC<WorkbookIngestionPanelProps> = ({
  modelManifest,
  ingestionReport,
  industry,
  lineCount,
}) => {
  const reports = normalizeReports(ingestionReport ?? undefined);
  const graph = modelManifest?.sheet_graph ?? [];
  const confidence = modelManifest?.confidence;
  const primary = reports[0];
  const warnings = reports.flatMap((r) => r.warnings ?? []);
  const zeroSpend = reports.some((r) => r.quality?.zero_spend_warning);
  const mappingNote = reports.map((r) => r.quality?.column_mapping_note).find(Boolean);

  if (!reports.length && !graph.length) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <FactVsInferenceLabel kind="fact" />
        <p className="text-xs font-semibold uppercase text-brand-muted">Workbook</p>
      </div>

      {modelManifest?.ingestion_strategy && (
        <p className="text-xs text-brand-muted">
          Strategy: <span className="font-mono text-brand-ink">{modelManifest.ingestion_strategy}</span>
          {industry ? (
            <>
              {' '}
              · Sector: <span className="text-brand-ink">{sectorLabel(industry)}</span>
            </>
          ) : null}
          {lineCount != null && lineCount > 0 ? (
            <>
              {' '}
              · <span className="text-brand-ink">{lineCount.toLocaleString()} lines</span> analyzed
            </>
          ) : null}
        </p>
      )}

      {confidence != null && confidence < 0.7 && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          Workbook structure confidence is low ({Math.round(confidence * 100)}%). Verify the ingested
          worksheet matches your raw spend data.
        </p>
      )}

      {lineCount === 0 && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          No spend lines were parsed. Check that a transactional sheet (supplier + amount columns) exists
          and is not named only as a dashboard tab.
        </p>
      )}

      {zeroSpend && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          Rows were ingested but parsed spend totals are zero. Re-run analysis after fixing column layout,
          or use a flat file with explicit Amount and Description columns (see data/samples/).
        </p>
      )}

      {warnings.map((w) => (
        <p
          key={w}
          className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5"
        >
          {w}
        </p>
      ))}

      {mappingNote && (
        <p className="text-xs text-brand-muted border-l-2 border-deloitte-green pl-2">{mappingNote}</p>
      )}

      {primary?.layout === 'hierarchical_expense' && (
        <p className="text-xs text-brand-muted">
          Detected hierarchical expense / P&L layout (line items + period amount columns).
        </p>
      )}

      {graph.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase text-brand-muted mb-1">Sheet roles</p>
          <ul className="text-xs space-y-1">
            {graph.map((node) => (
              <li key={node.sheet_name} className="flex justify-between gap-2">
                <span className="text-brand-ink truncate">{node.sheet_name}</span>
                <span className="text-brand-muted shrink-0 font-mono">{node.role}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {reports.map((rep, idx) => (
        <div key={rep.source_file ?? idx}>
          {rep.source_file && (
            <p className="text-[10px] text-brand-muted mb-1">{rep.source_file}</p>
          )}
          {(rep.sheets_ingested?.length ?? 0) > 0 && (
            <div className="mb-2">
              <p className="text-[10px] font-semibold uppercase text-emerald-800 mb-1">Ingested</p>
              <ul className="text-xs text-brand-ink space-y-0.5">
                {rep.sheets_ingested!.map((s) => (
                  <li key={s.sheet}>
                    <span className="font-medium">{s.sheet}</span> — {s.rows?.toLocaleString() ?? '?'} rows
                    {s.strategy ? ` (${s.strategy})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(rep.sheets_skipped?.length ?? 0) > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase text-brand-muted mb-1">Skipped</p>
              <ul className="text-xs text-brand-muted space-y-0.5">
                {rep.sheets_skipped!.slice(0, 6).map((s) => (
                  <li key={s.sheet}>
                    {s.sheet} — {s.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}

      {modelManifest?.ingestion_notes && (
        <p className="text-xs text-brand-muted italic">{modelManifest.ingestion_notes}</p>
      )}
    </div>
  );
};
