import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { DiagnosticValueBridge } from './DiagnosticValueBridge';

const sampleRows = [
  {
    lever_id: 'a',
    lever_name: 'Cloud rightsizing',
    p10_cr: 15,
    p50_cr: 25,
    p90_cr: 35,
    base_spend_cr: 120,
    base_spend_label: 'IT & Technology',
    complexity_tier: 'low',
    savings_type_label: 'Hard savings',
    value_derivation: { savings_rate_p50_pct: 22 },
  },
  {
    lever_id: 'b',
    lever_name: 'Vendor renegotiation',
    p10_cr: 8,
    p50_cr: 15,
    p90_cr: 22,
    complexity_tier: 'medium',
  },
];

describe('DiagnosticValueBridge', () => {
  it('renders per-lever sliders and portfolio summary', () => {
    render(
      <DiagnosticValueBridge
        rows={sampleRows}
        totalP50Cr={40}
        annualRevenueCr={2000}
      />,
    );

    expect(screen.getByLabelText('Value at table bridge')).toBeTruthy();
    expect(screen.getByText('Portfolio value')).toBeTruthy();
    expect(screen.getByText('All levers at expected (P50)')).toBeTruthy();
    expect(screen.getByLabelText('Uncertainty for Cloud rightsizing')).toBeTruthy();
    expect(screen.getByLabelText('Uncertainty for Vendor renegotiation')).toBeTruthy();
    expect(screen.getByText('Portfolio total')).toBeTruthy();
  });

  it('updates a single lever when its slider moves', () => {
    render(<DiagnosticValueBridge rows={sampleRows} totalP50Cr={40} />);

    expect(screen.getByText('₹40 Cr')).toBeTruthy();

    const cloudSlider = screen.getByLabelText('Uncertainty for Cloud rightsizing');
    fireEvent.change(cloudSlider, { target: { value: '10' } });

    expect(screen.getByText('Custom per-lever scenarios')).toBeTruthy();
    expect(screen.queryByText('₹40 Cr')).toBeNull();
  });
});
