/**
 * InitiativeDrawer — business-perspective detail sections render when present
 * and stay hidden when absent.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { InitiativeDrawer } from '../components/PageComponents/CostRoom/InitiativeDrawer';
import type { Initiative, InitiativeProvenance } from '../types';

const base: Initiative = {
  initiative_id: 'i1',
  category: 'IT & Telecom',
  lever: 'License Rightsizing',
  stage: 'identified',
  net_npv: 320,
  p50_savings: 360,
};

const enriched: Initiative = {
  ...base,
  business_rationale: 'License Rightsizing addresses shelfware above peer norm in IT & Telecom.',
  owner_role: 'Chief Information Officer / IT Finance Lead',
  business_sponsor: 'CIO and CFO',
  affected_vendors: [{ supplier: 'Oracle', spend: 600, share_of_category_pct: 60, avg_payment_terms_days: 30 }],
  contract_levers: ['Right-size licenses at renewal and remove shelfware'],
  risks: [{ risk: 'Negotiated savings erode over time', severity: 'high', mitigation: 'Lock ratchet clauses' }],
  kpis: [{ metric: 'License / seat utilization (%)', cadence: 'monthly' }],
  change_management: {
    stakeholders: ['Application owners', 'End users'],
    comms_cadence: 'Bi-weekly FinOps review',
    resistance_points: ['Shadow IT'],
  },
  phasing_narrative: 'Tactical initiative phased 25% / 38% / 38% across Years 1–3.',
};

describe('InitiativeDrawer business detail', () => {
  it('renders the business-perspective sections when present', () => {
    render(
      <InitiativeDrawer initiative={enriched} open onClose={() => {}} percentileBand="p50" currency="INR" />,
    );
    expect(screen.getByText('Business rationale')).toBeInTheDocument();
    expect(screen.getByText('Owner & accountability')).toBeInTheDocument();
    expect(screen.getByText('Chief Information Officer / IT Finance Lead')).toBeInTheDocument();
    expect(screen.getByText('Affected vendors')).toBeInTheDocument();
    expect(screen.getByText('Oracle')).toBeInTheDocument();
    expect(screen.getByText('Contract & commercial levers')).toBeInTheDocument();
    expect(screen.getByText('Risks & mitigations')).toBeInTheDocument();
    expect(screen.getByText(/Negotiated savings erode/)).toBeInTheDocument();
    expect(screen.getByText('KPIs')).toBeInTheDocument();
    expect(screen.getByText('Change management')).toBeInTheDocument();
    expect(screen.getByText('Phasing')).toBeInTheDocument();
  });

  it('hides the sections when the fields are absent', () => {
    render(
      <InitiativeDrawer initiative={base} open onClose={() => {}} percentileBand="p50" currency="INR" />,
    );
    expect(screen.queryByText('Business rationale')).not.toBeInTheDocument();
    expect(screen.queryByText('Owner & accountability')).not.toBeInTheDocument();
    expect(screen.queryByText('Affected vendors')).not.toBeInTheDocument();
    expect(screen.queryByText('Risks & mitigations')).not.toBeInTheDocument();
    expect(screen.queryByText('KPIs')).not.toBeInTheDocument();
    expect(screen.queryByText('Change management')).not.toBeInTheDocument();
  });
});

describe('InitiativeDrawer provenance trace', () => {
  const provenanceWithRows = (rowCount: number): InitiativeProvenance => ({
    initiative_id: 'i1',
    trace_steps: [{ step: 1, label: 'Savings value', value: 360 }],
    source_spend_rows: Array.from({ length: rowCount }, (_, i) => ({
      row_id: i + 1,
      supplier: `Supplier ${i + 1}`,
      amount_reporting: 1000 - i,
      fiscal_period: '2025-01',
    })),
    source_files: [],
  });

  it('truncates source rows to 8 with a caption', () => {
    render(
      <InitiativeDrawer
        initiative={base}
        open
        onClose={() => {}}
        percentileBand="p50"
        currency="INR"
        provenance={provenanceWithRows(10)}
      />,
    );
    expect(screen.getByText('Showing 8 of 10 source rows')).toBeInTheDocument();
    expect(screen.getByText('Supplier 8')).toBeInTheDocument();
    expect(screen.queryByText('Supplier 9')).not.toBeInTheDocument();
  });

  it('shows the empty-state copy when provenance is unavailable', () => {
    render(
      <InitiativeDrawer
        initiative={base}
        open
        onClose={() => {}}
        percentileBand="p50"
        currency="INR"
        provenance={null}
        provenanceLoading={false}
      />,
    );
    expect(screen.getByText('No source trace available for this initiative.')).toBeInTheDocument();
  });

  it('shows a loader while provenance is loading', () => {
    render(
      <InitiativeDrawer
        initiative={base}
        open
        onClose={() => {}}
        percentileBand="p50"
        currency="INR"
        provenanceLoading
      />,
    );
    expect(screen.getByText('Loading provenance…')).toBeInTheDocument();
  });
});

describe('InitiativeDrawer change history', () => {
  it('renders the 10 newest entries with a truncation caption', () => {
    const withLog: Initiative = {
      ...base,
      change_log: Array.from({ length: 12 }, (_, i) => ({
        ts: `2026-06-${String(i + 1).padStart(2, '0')}T10:00:00`,
        action: 'stage_change',
        detail: { from: 'identified', to: `stage_${i + 1}` },
      })),
    };
    render(
      <InitiativeDrawer initiative={withLog} open onClose={() => {}} percentileBand="p50" currency="INR" />,
    );
    expect(screen.getByText('Change history')).toBeInTheDocument();
    expect(screen.getByText('Showing 10 of 12 changes')).toBeInTheDocument();
    // Newest-first: the latest entry renders, the two oldest are cut.
    expect(screen.getByText(/stage_12/)).toBeInTheDocument();
    expect(screen.queryByText(/stage_2\b/)).not.toBeInTheDocument();
  });

  it('hides the section when there is no change log', () => {
    render(
      <InitiativeDrawer initiative={base} open onClose={() => {}} percentileBand="p50" currency="INR" />,
    );
    expect(screen.queryByText('Change history')).not.toBeInTheDocument();
  });
});
