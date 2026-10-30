import React, { useMemo, useState } from 'react';
import { formatAmount } from '../../../utils/formatInr';
import { copyText, downloadTextFile, toCsv, toTsv } from '../../../utils/exportTable';

export interface QueryResultLike {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

interface ResultsTableProps {
  result: QueryResultLike;
  currency: string;
}

type ColKind = 'currency' | 'number' | 'text';

const CURRENCY_COL_RE = /amount|spend|value|savings|npv|cost/i;

function inferKinds(columns: string[], rows: unknown[][]): ColKind[] {
  const sample = rows.slice(0, 50);
  return columns.map((col, j) => {
    if (CURRENCY_COL_RE.test(col)) return 'currency';
    let numeric = 0;
    let seen = 0;
    for (const row of sample) {
      const v = row[j];
      if (v === null || v === undefined || v === '') continue;
      seen += 1;
      if (typeof v === 'number' && Number.isFinite(v)) numeric += 1;
      else if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) numeric += 1;
    }
    return seen > 0 && numeric / seen >= 0.8 ? 'number' : 'text';
  });
}

function asNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

function compareCells(a: unknown, b: unknown, kind: ColKind): number {
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (kind === 'currency' || kind === 'number') {
    const na = asNumber(a) ?? 0;
    const nb = asNumber(b) ?? 0;
    return na - nb;
  }
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base' });
}

export const ResultsTable: React.FC<ResultsTableProps> = ({ result, currency }) => {
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  const kinds = useMemo(
    () => inferKinds(result.columns, result.rows),
    [result.columns, result.rows],
  );

  const sortedRows = useMemo(() => {
    if (sortCol === null) return result.rows;
    const kind = kinds[sortCol] ?? 'text';
    const idx = result.rows.map((_, i) => i);
    idx.sort((ia, ib) => {
      const cmp = compareCells(result.rows[ia][sortCol], result.rows[ib][sortCol], kind);
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return idx.map((i) => result.rows[i]);
  }, [result.rows, sortCol, sortDir, kinds]);

  const toggleSort = (j: number) => {
    if (sortCol === j) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(j);
      setSortDir('asc');
    }
  };

  const handleCopy = async () => {
    try {
      await copyText(toTsv(result.columns, sortedRows));
      setCopyStatus('Copied');
      setTimeout(() => setCopyStatus(null), 1500);
    } catch {
      setCopyStatus('Copy failed');
      setTimeout(() => setCopyStatus(null), 1500);
    }
  };

  const handleDownload = () => {
    downloadTextFile('query_results.csv', toCsv(result.columns, sortedRows));
  };

  const formatCell = (v: unknown, kind: ColKind): { text: string; title?: string } => {
    if (v === null || v === undefined) return { text: '' };
    if (kind === 'currency') {
      const n = asNumber(v);
      if (n === null) return { text: String(v) };
      return { text: formatAmount(n, currency), title: String(n) };
    }
    if (kind === 'number') {
      const n = asNumber(v);
      if (n === null) return { text: String(v) };
      return { text: n.toLocaleString(undefined, { maximumFractionDigits: 4 }) };
    }
    return { text: String(v) };
  };

  return (
    <div className="overflow-auto max-h-[420px] border border-brand-border rounded">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-brand-border bg-brand-surface-elevated px-2 py-1 text-xs text-brand-muted">
        <span>
          {result.row_count} rows · {result.elapsed_ms.toFixed(0)} ms
          {result.truncated ? ' · truncated' : ''}
        </span>
        <button
          type="button"
          className="rounded border border-brand-border px-2 py-0.5 hover:bg-brand-surface"
          onClick={() => void handleCopy()}
        >
          {copyStatus ?? 'Copy TSV'}
        </button>
        <button
          type="button"
          className="rounded border border-brand-border px-2 py-0.5 hover:bg-brand-surface"
          onClick={handleDownload}
        >
          Download CSV
        </button>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-brand-surface-elevated text-left sticky top-[29px] z-10">
            {result.columns.map((c, j) => (
              <th key={c} className="px-2 py-1 font-medium whitespace-nowrap">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 hover:underline"
                  onClick={() => toggleSort(j)}
                >
                  {c}
                  {sortCol === j ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, i) => (
            <tr key={i} className="border-t border-brand-border/50">
              {row.map((cell, j) => {
                const kind = kinds[j] ?? 'text';
                const { text, title } = formatCell(cell, kind);
                return (
                  <td
                    key={j}
                    title={title}
                    className={`px-2 py-1 whitespace-nowrap font-mono text-xs ${
                      kind === 'number' || kind === 'currency' ? 'text-right' : ''
                    }`}
                  >
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
