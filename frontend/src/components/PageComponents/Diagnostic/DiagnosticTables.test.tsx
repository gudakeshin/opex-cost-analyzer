import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { BenchmarkGapsTable, ValueAtTableTable } from './DiagnosticTables';

describe('DiagnosticTables collapsible rows', () => {
  it('expands benchmark gaps panel then row detail', () => {
    render(
      <BenchmarkGapsTable
        gaps={[
          {
            category: 'RND',
            category_name: 'R&D & Engineering',
            p50_pct: 10,
            p25_pct: 5,
            benchmark_p50_to_p25_band_cr: 100,
            commentary:
              'R&D & Engineering is modelled at 10% of revenue (industry median P50); ₹100 Cr savings potential if spend moves to P25 best-in-class (5%). Based on sector benchmark proxy.',
          },
        ]}
      />,
    );

    expect(screen.queryByText(/R&D & Engineering at 10% of revenue/)).toBeNull();

    expect(screen.getByText(/Not based on your company/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /Ranked category gaps/i }));

    expect(screen.getByText(/R&D & Engineering at 10% of revenue/)).toBeTruthy();
    expect(screen.queryByText('Full rationale')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /R&D & Engineering at 10%/ }));

    expect(screen.getByText('Full rationale')).toBeTruthy();
    expect(screen.getByText(/Based on sector benchmark proxy/)).toBeTruthy();
  });

  it('shows merged value table with expandable lever detail', () => {
    render(
      <ValueAtTableTable
        rows={[
          {
            lever_id: 'cloud',
            lever_name: 'Cloud rightsizing',
            p10_cr: 10,
            p50_cr: 25,
            p90_cr: 40,
            base_spend_cr: 120,
            base_spend_label: 'IT & Technology',
            rationale: 'Selected because IT spend is material in the benchmark profile.',
            calculation_note:
              'Expected (P50) = 22% × ₹120 Cr = ₹25 Cr. Pool: ₹120 Cr — IT addressable pool.',
            value_derivation: {
              savings_rate_p50_pct: 22,
              calculation_p50: 'Expected (P50) = 22% × ₹120 Cr = ₹25 Cr',
            },
          },
        ]}
        totalP50Cr={25}
      />,
    );

    expect(screen.getByText(/Not based on your company/)).toBeTruthy();
    expect(screen.getByLabelText('Value at table bridge')).toBeTruthy();
    expect(screen.getByText('Benchmark proxy')).toBeTruthy();
    expect(screen.getAllByText('Cloud rightsizing').length).toBeGreaterThan(0);
    expect(screen.getByText('Portfolio value')).toBeTruthy();
    expect(screen.queryByText('Lever detail table')).toBeNull();
    expect(screen.queryByText('Why selected')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Rationale & band detail/i }));

    expect(screen.getByText('Why selected')).toBeTruthy();
    expect(screen.getByText(/IT addressable pool/)).toBeTruthy();
  });
});
