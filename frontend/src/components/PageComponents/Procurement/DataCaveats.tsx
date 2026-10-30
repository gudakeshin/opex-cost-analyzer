import React from 'react';
import type { AnalysisInsightSnapshot } from '../../../types';

interface DataCaveatsProps {
  snapshot: AnalysisInsightSnapshot | null | undefined;
  /** Include the benchmark caveats (only relevant where peer figures are shown). */
  includeBenchmarks?: boolean;
  /** Include ingest warnings (rows dropped, FX defaults). Off where another panel already lists them. */
  includeIngestion?: boolean;
  className?: string;
}

/** Amber notes about how far the numbers can be trusted: dropped rows, FX defaults, illustrative benchmarks. */
export const DataCaveats: React.FC<DataCaveatsProps> = ({
  snapshot,
  includeBenchmarks = true,
  includeIngestion = true,
  className = '',
}) => {
  if (!snapshot) return null;
  const notes: string[] = includeIngestion ? [...(snapshot.ingestion_warnings ?? [])] : [];
  if (includeBenchmarks) {
    for (const w of snapshot.benchmark_warnings ?? []) {
      if (!notes.includes(w)) notes.push(w);
    }
    if (snapshot.benchmarks_illustrative && !notes.some((n) => /illustrative/i.test(n))) {
      notes.push('Peer benchmarks are illustrative (no sample behind them); treat peer gaps as directional.');
    }
  }
  if (notes.length === 0) return null;
  return (
    <ul
      className={`space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-900 ${className}`}
      aria-label="Data caveats"
    >
      {notes.map((n) => (
        <li key={n} className="flex gap-1.5">
          <span aria-hidden>⚠</span>
          <span>{n}</span>
        </li>
      ))}
    </ul>
  );
};
