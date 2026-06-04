import React from 'react';
import {
  activeEngagementConflicts,
  conflictSummaryMessage,
  primaryDetectedCompany,
  type EngagementSanityConflict,
} from '../../../utils/engagementConflict';
import type { SessionManifest } from '../../../types';

interface EngagementConflictBannerProps {
  manifest: SessionManifest | null;
  sessionId: string | null;
  dismissedKeys: Set<string>;
  onDismiss: (conflict: EngagementSanityConflict) => void;
  onUseDetectedCompany: (company: string) => void | Promise<void>;
  onKeepEngagementCompany: () => void;
  resolving?: boolean;
}

export const EngagementConflictBanner: React.FC<EngagementConflictBannerProps> = ({
  manifest,
  sessionId,
  dismissedKeys,
  onDismiss,
  onUseDetectedCompany,
  onKeepEngagementCompany,
  resolving,
}) => {
  const conflicts = activeEngagementConflicts(manifest, sessionId, dismissedKeys);
  if (conflicts.length === 0) return null;

  const detected = primaryDetectedCompany(conflicts);
  const engagementCompany =
    conflicts[0]?.engagement_company ??
    manifest?.diagnostic_result?.company_name ??
    manifest?.company_name;

  return (
    <div
      className="mx-4 md:mx-6 mt-3 shrink-0 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      role="alert"
    >
      <p className="font-semibold text-amber-900">Engagement context mismatch</p>
      <p className="mt-1 text-amber-900/90">{conflictSummaryMessage(conflicts)}</p>
      <p className="mt-2 text-xs text-amber-800">
        Session company: <span className="font-medium">{engagementCompany ?? '—'}</span>
        {detected ? (
          <>
            {' '}
            · Upload suggests: <span className="font-medium">{detected}</span>
          </>
        ) : null}
        {manifest?.diagnostic_result ? (
          <span className="ml-1 text-amber-700">(diagnostic context active)</span>
        ) : null}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {detected && (
          <button
            type="button"
            disabled={resolving}
            onClick={() => void onUseDetectedCompany(detected)}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-900 text-white hover:bg-amber-950 disabled:opacity-50"
          >
            Use {detected} for this session
          </button>
        )}
        <button
          type="button"
          disabled={resolving}
          onClick={onKeepEngagementCompany}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-amber-400 bg-white text-amber-900 hover:bg-amber-100 disabled:opacity-50"
        >
          Keep {engagementCompany ?? 'engagement'} context
        </button>
        <button
          type="button"
          onClick={() => conflicts.forEach(onDismiss)}
          className="text-xs px-3 py-1.5 rounded-lg text-amber-800 hover:underline"
        >
          Dismiss for now
        </button>
      </div>
      <p className="mt-2 text-[11px] text-amber-700">
        Analysis will still run, but benchmarks and deep-research context may not match uploaded spend
        until you align the company or replace the file.
      </p>
    </div>
  );
};
