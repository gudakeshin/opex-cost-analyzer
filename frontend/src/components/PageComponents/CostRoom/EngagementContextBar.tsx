import React from 'react';
import { Link } from 'react-router-dom';
import { useSession } from '../../../context/SessionContext';
import { useAudience } from '../../../context/AudienceContext';
import { formatIndustryLabel } from '../../../utils/formatInr';
import { isClientEngagementReady } from '../../../utils/engagement';

export const EngagementContextBar: React.FC = () => {
  const { engagement, hasAnalysis } = useSession();
  const { toggleAudience, audience } = useAudience();
  const clientReady = isClientEngagementReady(hasAnalysis, engagement.company_name);

  return (
    <header className="border-b border-brand-border bg-white/80 backdrop-blur-sm -mx-4 md:-mx-6 lg:-mx-8 px-4 md:px-6 lg:px-8 py-4 mb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1 min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-brand-muted">
            Deloitte · Live Cost Room
          </p>
          <h1 className="text-xl md:text-2xl font-bold text-brand-ink truncate">
            {clientReady ? engagement.company_name : 'Client portfolio'}
            {clientReady && (
              <span className="font-normal text-brand-muted">
                {' '}
                · {formatIndustryLabel(engagement.industry)}
              </span>
            )}
          </h1>
          {!clientReady && (
            <p className="text-sm text-brand-muted">
              Run analysis on the{' '}
              <Link to="/" className="text-brand-navy font-medium hover:text-deloitte-green">
                Analysis
              </Link>{' '}
              page to load this client&apos;s executive Cost Room.
            </p>
          )}
          <p className="text-sm text-brand-muted">
            Week {engagement.engagement_week} of {engagement.engagement_weeks_total}
            <span className="mx-2">·</span>
            <span className="text-brand-navy font-medium">{engagement.gate_label}</span>
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs text-brand-muted hidden sm:inline">Group CFO · SSO</span>
          <button
            type="button"
            onClick={toggleAudience}
            className="text-xs px-3 py-1.5 rounded-lg border border-brand-border text-brand-ink hover:bg-brand-surface-muted"
          >
            {audience === 'executive' ? 'Consultant mode' : 'Executive mode'}
          </button>
        </div>
      </div>
    </header>
  );
};
