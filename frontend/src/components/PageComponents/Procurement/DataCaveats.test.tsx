import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DataCaveats } from './DataCaveats';
import type { AnalysisInsightSnapshot } from '../../../types';

const base: AnalysisInsightSnapshot = { total_spend: 1, reporting_currency: 'INR', top_categories: [] };

describe('DataCaveats', () => {
  it('lists ingest warnings and flags illustrative benchmarks once', () => {
    render(
      <DataCaveats
        snapshot={{
          ...base,
          ingestion_warnings: ['1 of 4 rows were dropped.'],
          benchmarks_illustrative: true,
        }}
      />,
    );
    expect(screen.getByRole('list', { name: 'Data caveats' })).toBeInTheDocument();
    expect(screen.getByText('1 of 4 rows were dropped.')).toBeInTheDocument();
    expect(screen.getAllByText(/illustrative/i)).toHaveLength(1);
  });

  it('can omit ingest warnings (shown elsewhere) and renders nothing when there is nothing to say', () => {
    const { container, rerender } = render(
      <DataCaveats snapshot={{ ...base, ingestion_warnings: ['dropped'] }} includeIngestion={false} />,
    );
    expect(container).toBeEmptyDOMElement();
    rerender(<DataCaveats snapshot={base} />);
    expect(container).toBeEmptyDOMElement();
  });
});
