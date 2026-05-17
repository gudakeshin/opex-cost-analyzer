import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { PageHeader } from '../components/Common/PageHeader';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { useSession } from '../context/SessionContext';
import { apiGet, getApiErrorMessage } from '../hooks/useApi';
import type { SessionSummary } from '../types';

function formatDate(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function formatRevenue(amount?: number, currency?: string): string {
  if (!amount) return '—';
  const sym = currency === 'INR' ? '₹' : currency === 'USD' ? '$' : (currency ?? '') + ' ';
  if (amount >= 10_000_000) return `${sym}${(amount / 10_000_000).toFixed(1)} Cr`;
  if (amount >= 100_000) return `${sym}${(amount / 100_000).toFixed(1)} L`;
  return `${sym}${amount.toLocaleString()}`;
}

export const SessionHistory: React.FC = () => {
  const { setSessionId, sessionId } = useSession();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SessionSummary[]>('/api/v1/sessions')
      .then(setSessions)
      .catch((err) => setError(getApiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  const resumeSession = (sid: string) => {
    setSessionId(sid);
    navigate('/');
  };

  return (
    <MainLayout hideHeader>
      <PageHeader
        title="History"
        subtitle="Browse and resume previous engagements"
      />

      {error && (
        <Alert variant="error" title="Could not load sessions" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="mt-12">
          <Loader label="Loading sessions…" />
        </div>
      ) : sessions.length === 0 ? (
        <div className="mt-16 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gray-50 border border-brand-border flex items-center justify-center">
            <svg className="w-8 h-8 text-brand-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h3 className="text-base font-semibold text-brand-ink mb-1">No past sessions</h3>
          <p className="text-sm text-brand-muted mb-4">
            Upload spend data in the Analysis tab to start your first engagement.
          </p>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="px-5 py-2.5 rounded-xl bg-deloitte-green text-white text-sm font-medium hover:bg-[#6fa31e] transition-colors"
          >
            Go to Analysis →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mt-6">
          {sessions.map((s) => (
            <div
              key={s.session_id}
              className={`bg-white border rounded-xl p-5 flex flex-col gap-3 hover:shadow-md transition-shadow ${
                s.session_id === sessionId ? 'border-deloitte-green ring-1 ring-deloitte-green/30' : 'border-brand-border'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-semibold text-brand-ink text-sm leading-snug">
                    {s.company_name}
                  </p>
                  {s.industry && (
                    <p className="text-xs text-brand-muted mt-0.5 capitalize">{s.industry}</p>
                  )}
                </div>
                {s.has_analysis ? (
                  <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-green-50 text-green-700 border border-green-200">
                    Analysed
                  </span>
                ) : (
                  <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-50 text-brand-muted border border-brand-border">
                    No analysis
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-brand-muted">
                <span>Created</span>
                <span className="text-brand-ink font-medium">{formatDate(s.created_at)}</span>
                <span>Revenue</span>
                <span className="text-brand-ink font-medium">{formatRevenue(s.annual_revenue, s.currency)}</span>
                <span>Files</span>
                <span className="text-brand-ink font-medium">{s.file_count}</span>
                {s.top_savings_estimate != null && (
                  <>
                    <span>Savings est.</span>
                    <span className="text-deloitte-green font-semibold">
                      {formatRevenue(s.top_savings_estimate, s.currency)}
                    </span>
                  </>
                )}
              </div>

              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => resumeSession(s.session_id)}
                  className="flex-1 text-xs px-3 py-1.5 rounded-lg bg-deloitte-green text-white font-medium hover:bg-[#6fa31e] transition-colors"
                >
                  Resume →
                </button>
                {s.session_id === sessionId && (
                  <span className="text-[10px] text-deloitte-green self-center font-medium">Active</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </MainLayout>
  );
};
