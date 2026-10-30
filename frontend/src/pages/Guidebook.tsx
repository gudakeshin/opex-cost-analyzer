import React, { useEffect, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { PageHeader } from '../components/Common/PageHeader';
import { Card } from '../components/Common/Card';
import { Badge } from '../components/Common/Badge';
import { CollapsiblePanel } from '../components/Common/CollapsibleDetail';
import {
  GUIDEBOOK_ACCEPTED_FORMATS,
  GUIDEBOOK_MISSING_IMPACT,
  GUIDEBOOK_TIERS,
  type GuidebookTierId,
} from '../data/guidebookDataSources';

const TIER_BADGE_TONE: Record<
  (typeof GUIDEBOOK_TIERS)[number]['badgeTone'],
  'warning' | 'success' | 'default' | 'error'
> = {
  required: 'warning',
  deep: 'success',
  enrichment: 'default',
  external: 'default',
  sector: 'default',
};

const TIER_NAV: { id: GuidebookTierId; short: string }[] = [
  { id: 'tier1', short: 'Tier 1' },
  { id: 'tier2', short: 'Tier 2' },
  { id: 'tier3', short: 'Tier 3' },
  { id: 'tier4', short: 'Tier 4' },
  { id: 'tier5', short: 'Tier 5' },
];

function scrollToTier(id: GuidebookTierId) {
  document.getElementById(`guidebook-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export const Guidebook: React.FC = () => {
  const [activeTier, setActiveTier] = useState<GuidebookTierId>('tier1');

  useEffect(() => {
    const sections = TIER_NAV.map((t) => document.getElementById(`guidebook-${t.id}`)).filter(Boolean);
    if (!sections.length) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => (b.intersectionRatio ?? 0) - (a.intersectionRatio ?? 0));
        const top = visible[0];
        if (top?.target?.id) {
          const tierId = top.target.id.replace('guidebook-', '') as GuidebookTierId;
          setActiveTier(tierId);
        }
      },
      { rootMargin: '-20% 0px -55% 0px', threshold: [0, 0.15, 0.4] },
    );

    sections.forEach((el) => observer.observe(el!));
    return () => observer.disconnect();
  }, []);

  return (
    <MainLayout hideHeader title="Guidebook">
      <PageHeader
        title="Guidebook"
        subtitle="Client data sources for deep OpEx analysis — what to request, why it matters, and how each input adds value"
      />

      <Card className="bg-white border-brand-border mb-6">
        <p className="text-sm text-brand-ink leading-relaxed">
          Use this guide when scoping a new engagement or issuing a Week-1 data request. Tiers are ordered by
          dependency: Tier 1 must be in place before the platform runs analysis; Tier 2 unlocks the full value
          bridge and executive synthesis; Tiers 3–5 increase confidence, lever depth, and sector specificity.
        </p>
        <ul className="mt-4 space-y-1.5 text-sm text-brand-muted">
          {GUIDEBOOK_ACCEPTED_FORMATS.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="text-brand-primary shrink-0">•</span>
              <span>{line}</span>
            </li>
          ))}
        </ul>
      </Card>

      <nav
        className="sticky top-14 md:top-0 z-20 -mx-1 mb-6 flex flex-wrap gap-2 rounded-lg border border-brand-border bg-white/95 backdrop-blur px-3 py-3 shadow-sm"
        aria-label="Guidebook tiers"
      >
        {TIER_NAV.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => scrollToTier(t.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
              activeTier === t.id
                ? 'bg-deloitte-green text-black'
                : 'bg-brand-surface-muted text-brand-ink hover:bg-brand-border/40'
            }`}
          >
            {t.short}
          </button>
        ))}
      </nav>

      <div className="space-y-10">
        {GUIDEBOOK_TIERS.map((tier) => (
          <section key={tier.id} id={`guidebook-${tier.id}`} className="scroll-mt-28">
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <h2 className="text-lg font-bold text-brand-ink">{tier.title}</h2>
              <Badge tone={TIER_BADGE_TONE[tier.badgeTone]}>{tier.badge}</Badge>
            </div>
            <p className="text-sm text-brand-muted mb-1">{tier.subtitle}</p>
            <p className="text-sm text-brand-ink leading-relaxed mb-5">{tier.overview}</p>

            <div className="space-y-3">
              {tier.sources.map((source) => (
                <CollapsiblePanel
                  key={source.id}
                  title={source.name}
                  summary={source.whatToProvide}
                  defaultOpen={tier.id === 'tier1' && source.id === 't1-spend-ledger'}
                >
                  <div className="grid gap-4 sm:grid-cols-1">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-1">
                        What to provide
                      </p>
                      <p className="text-sm text-brand-ink leading-relaxed">{source.whatToProvide}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-1">
                        Why it is required
                      </p>
                      <p className="text-sm text-brand-ink leading-relaxed">{source.whyRequired}</p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-brand-primary mb-1">
                        How it adds value
                      </p>
                      <p className="text-sm text-brand-ink leading-relaxed">{source.valueAdded}</p>
                    </div>
                    {source.platformSignals && source.platformSignals.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-1">
                          Platform signals
                        </p>
                        <ul className="text-xs text-brand-muted space-y-1 font-mono">
                          {source.platformSignals.map((sig) => (
                            <li key={sig}>{sig}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </CollapsiblePanel>
              ))}
            </div>
          </section>
        ))}
      </div>

      <section className="mt-12 mb-8" id="guidebook-cost-room">
        <h2 className="text-lg font-bold text-brand-ink mb-2">Cost Room workflow</h2>
        <p className="text-sm text-brand-muted mb-4">
          The Live Cost Room is the Week 4+ initiative command center for consultants and executives. It
          turns analysis outputs into a governable savings portfolio.
        </p>
        <Card className="bg-white border-brand-border mb-4">
          <h3 className="text-sm font-semibold text-brand-ink mb-3">Analysis → Cost Room data flow</h3>
          <ol className="text-sm text-brand-ink space-y-2 list-decimal list-inside">
            <li>
              Upload spend in <strong>Analysis</strong> and run OPAR analysis. Skill outputs (value bridge,
              savings model, FP&amp;A analyzers) are stored in session memory.
            </li>
            <li>
              When analysis completes, initiatives are <strong>seeded automatically</strong> into the pipeline
              store from the business-case builder output.
            </li>
            <li>
              Open <strong>Cost Room</strong> to filter the portfolio, toggle P10/P50/P90 bands, stress-test
              macro scenarios, accept/defer/reject initiatives, and resolve data conflicts.
            </li>
            <li>
              Drill into any initiative to view assumptions, source spend rows, uploaded files, milestones,
              and record realized savings actuals.
            </li>
            <li>
              Export the current view as a <strong>deck</strong> (business case DOCX) or <strong>Excel</strong>{' '}
              PMO portfolio workbook from the trust footer.
            </li>
          </ol>
        </Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card className="bg-white border-brand-border">
            <h3 className="text-sm font-semibold text-brand-ink mb-2">Consultant mode</h3>
            <ul className="text-sm text-brand-muted space-y-1.5 list-disc list-inside">
              <li>Accept / defer / reject with audit trail (AQS ≥ 0.65 for Gate-2 accept)</li>
              <li>Data conflict resolution and exception inbox</li>
              <li>FP&amp;A detail tabs: Trends, BvA, Payment Terms, Cost-to-Serve</li>
              <li>Entity consolidation and full trust rail</li>
            </ul>
          </Card>
          <Card className="bg-white border-brand-border">
            <h3 className="text-sm font-semibold text-brand-ink mb-2">Executive mode</h3>
            <ul className="text-sm text-brand-muted space-y-1.5 list-disc list-inside">
              <li>Engagement context bar with company, gate, and audience toggle</li>
              <li>Read-only portfolio with EBITDA bps, sustainability, and addressability dots</li>
              <li>Scenario controls and value bridge for Audit Committee walkthroughs</li>
              <li>Conflicts and FP&amp;A panels hidden for a cleaner C-suite view</li>
            </ul>
          </Card>
        </div>
      </section>

      <section className="mt-12 mb-8">
        <h2 className="text-lg font-bold text-brand-ink mb-2">Impact when data is missing</h2>
        <p className="text-sm text-brand-muted mb-4">
          The Observe and Reflect phases surface these gaps through missing_fields, data quality score, and SME
          critique probes.
        </p>
        <Card className="bg-white border-brand-border overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-brand-border bg-brand-surface-muted">
                <th className="text-left px-4 py-3 font-semibold text-brand-ink">Missing input</th>
                <th className="text-left px-4 py-3 font-semibold text-brand-ink">Effect on analysis</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-brand-border">
              {GUIDEBOOK_MISSING_IMPACT.map((row) => (
                <tr key={row.missing}>
                  <td className="px-4 py-3 font-medium text-brand-ink align-top">{row.missing}</td>
                  <td className="px-4 py-3 text-brand-muted align-top">{row.effect}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>

      <section className="rounded-lg border border-brand-border bg-brand-surface-muted/50 px-4 py-4 mb-6">
        <h3 className="text-sm font-semibold text-brand-ink mb-2">Suggested client checklist (Week 0–1)</h3>
        <ol className="text-sm text-brand-muted space-y-2 list-decimal list-inside">
          <li>Company name, sector, annual revenue (Cr), aggregated headcount</li>
          <li>Transactional spend ledger (12–36 months) with supplier, amount, category/GL, date</li>
          <li>GL/AP detail, budget vs actual, vendor master, contract register</li>
          <li>Supporting documents and deep research URLs or approval to run research</li>
          <li>Sector-pack KPIs for the engagement industry code</li>
        </ol>
      </section>
    </MainLayout>
  );
};
