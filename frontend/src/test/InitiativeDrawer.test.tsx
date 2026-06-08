/**
 * InitiativeDrawer — business-perspective detail sections render when present
 * and stay hidden when absent.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { InitiativeDrawer } from '../components/PageComponents/CostRoom/InitiativeDrawer';
import type { Initiative } from '../types';

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
