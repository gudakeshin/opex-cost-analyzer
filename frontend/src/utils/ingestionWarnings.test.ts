import { describe, expect, it } from 'vitest';
import {
  ingestionQualityFromManifest,
  showZeroSpendIngestionWarning,
} from './ingestionWarnings';
import type { SessionManifest, SessionResponse } from '../types';

describe('ingestionWarnings', () => {
  it('surfaces zero-spend quality flag from manifest', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      ingestion_report: {
        quality: { zero_spend_warning: true, rows_parsed: 10, total_amount: 0 },
        sheets_ingested: [{ sheet: 'Data', rows: 10 }],
      },
    };
    expect(ingestionQualityFromManifest(manifest)?.zero_spend_warning).toBe(true);
    expect(showZeroSpendIngestionWarning(manifest, null)).toBe(true);
  });

  it('warns when analysis total spend is zero despite ingested rows', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      ingestion_report: {
        sheets_ingested: [{ sheet: 'Ledger', rows: 5 }],
      },
    };
    const analysis = {
      skill_outputs: { 'spend-profiler': { total_spend: 0, category_profile: [] } },
    } as unknown as SessionResponse;
    expect(showZeroSpendIngestionWarning(manifest, analysis)).toBe(true);
  });
});
