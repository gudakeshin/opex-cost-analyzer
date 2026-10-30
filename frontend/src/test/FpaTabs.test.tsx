/**
 * FP&A detail tabs — graceful `*_available: false` rendering (locks the
 * 200-with-reason endpoint contract) and truncation captions.
 * recharts renders zero-size in jsdom, so assertions target captions/tables.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { TrendsTab } from '../components/PageComponents/CostRoom/TrendsTab';
import { BvaTab } from '../components/PageComponents/CostRoom/BvaTab';
import { PaymentTermsTab } from '../components/PageComponents/CostRoom/PaymentTermsTab';
import { CostToServeTab } from '../components/PageComponents/CostRoom/CostToServeTab';

const idle = { loading: false, error: null as string | null, currency: 'INR' };

describe('FP&A tabs unavailable state', () => {
  it('TrendsTab renders the reason when temporal analysis is unavailable', () => {
    render(
      <TrendsTab {...idle} data={{ temporal_available: false, reason: 'Run analysis first.' }} />,
    );
    expect(screen.getByText('Run analysis first.')).toBeInTheDocument();
  });

  it('BvaTab renders the reason when BvA is unavailable', () => {
    render(<BvaTab {...idle} data={{ bva_available: false, reason: 'No budget lines detected.' }} />);
    expect(screen.getByText('No budget lines detected.')).toBeInTheDocument();
  });

  it('PaymentTermsTab renders the reason when payment terms are unavailable', () => {
    render(
      <PaymentTermsTab
        {...idle}
        data={{ payment_terms_available: false, reason: 'No payment terms column.' }}
      />,
    );
    expect(screen.getByText('No payment terms column.')).toBeInTheDocument();
  });

  it('CostToServeTab renders the reason when cost-to-serve is unavailable', () => {
    render(
      <CostToServeTab
        {...idle}
        data={{ cost_to_serve_available: false, reason: 'No spend lines provided.' }}
      />,
    );
    expect(screen.getByText('No spend lines provided.')).toBeInTheDocument();
  });

  it('tabs render an error message over data', () => {
    render(<BvaTab data={null} loading={false} error="Server unreachable" currency="INR" />);
    expect(screen.getByText('Server unreachable')).toBeInTheDocument();
  });
});

describe('FP&A tabs truncation captions', () => {
  it('BvaTab captions the chart when variances exceed 10', () => {
    const variances = Array.from({ length: 12 }, (_, i) => ({
      category_id: `cat-${i + 1}`,
      category_name: `Category ${i + 1}`,
      actual_spend: 100,
      budget_spend: 90,
      total_variance: 10,
      flag: 'over_budget',
    }));
    render(<BvaTab {...idle} data={{ bva_available: true, variances }} />);
    expect(screen.getByText('Showing top 10 of 12')).toBeInTheDocument();
    // The table itself shows every variance.
    expect(screen.getByText('Category 12')).toBeInTheDocument();
  });

  it('TrendsTab captions and truncates the category table to 8 rows', () => {
    const categoryTrends = Array.from({ length: 10 }, (_, i) => ({
      category_id: `cat-${i + 1}`,
      category_name: `Category ${i + 1}`,
      trend_direction: 'rising',
      cagr_pct: 5,
    }));
    render(
      <TrendsTab
        {...idle}
        data={{ temporal_available: true, period_trends: [], category_trends: categoryTrends }}
      />,
    );
    expect(screen.getByText('Showing top 8 of 10')).toBeInTheDocument();
    expect(screen.getByText('Category 8')).toBeInTheDocument();
    expect(screen.queryByText('Category 9')).not.toBeInTheDocument();
  });

  it('CostToServeTab captions the chart when drivers exceed 8', () => {
    const drivers = Array.from({ length: 10 }, (_, i) => ({
      category_id: `cat-${i + 1}`,
      category_name: `Category ${i + 1}`,
      spend: 100,
      pct_of_opex: 10,
    }));
    render(
      <CostToServeTab {...idle} data={{ cost_to_serve_available: true, top_cost_drivers: drivers }} />,
    );
    expect(screen.getByText('Showing top 8 of 10')).toBeInTheDocument();
    // The driver table still lists everything.
    expect(screen.getByText('Category 10')).toBeInTheDocument();
  });
});
