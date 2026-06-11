import React, { useEffect, useState } from 'react';
import { SECTOR_OPTIONS } from '../../../constants/sectors';
import { Select } from '../../Common/Select';
import {
  activeEngagementConflicts,
  conflictSummaryMessage,
  engagementIndustryLabel,
  primaryDetectedCompany,
  primaryDetectedIndustry,
  primaryDetectedIndustryLabel,
  type EngagementSanityConflict,
} from '../../../utils/engagementConflict';
import { effectiveAnalysisIndustry } from '../../../utils/engagementContext';
import type { EngagementMeta, SessionManifest } from '../../../types';

interface EngagementConflictBannerProps {
  manifest: SessionManifest | null;
  engagement: Pick<EngagementMeta, 'industry' | 'detected_industry'>;
  sessionId: string | null;
  dismissedKeys: Set<string>;
  onDismiss: (conflict: EngagementSanityConflict) => void;
  onUseDetectedCompany: (company: string) => void | Promise<void>;
  onApplySector: (industry: string) => void | Promise<void>;
  onKeepEngagementCompany: () => void;
  resolving?: boolean;
}

export const EngagementConflictBanner: React.FC<EngagementConflictBannerProps> = ({
  manifest,
  engagement,
  sessionId,
  dismissedKeys,
  onDismiss,
  onUseDetectedCompany,
  onApplySector,
  onKeepEngagementCompany,
  resolving,
}) => {
  const conflicts = activeEngagementConflicts(manifest, sessionId, dismissedKeys);
  const detectedIndustry = primaryDetectedIndustry(conflicts);
  const currentIndustry = effectiveAnalysisIndustry(manifest, engagement);
  const [selectedSector, setSelectedSector] = useState(
    detectedIndustry || currentIndustry || '',
  );

  useEffect(() => {
    setSelectedSector(detectedIndustry || currentIndustry || '');
  }, [detectedIndustry, currentIndustry, sessionId]);

  if (conflicts.length === 0) return null;

  const detectedIndustryLabel = primaryDetectedIndustryLabel(conflicts);
  const engagementCompany =
    conflicts.find((c) => c.engagement_company)?.engagement_company ??
    manifest?.diagnostic_result?.company_name ??
    manifest?.company_name;
  const engagementIndustry = engagementIndustryLabel(conflicts, manifest);
  const hasCompanyConflict = conflicts.some(
    (c) => c.kind === 'upload_company_mismatch' || c.kind === 'uploads_disagree',
  );
  const hasIndustryConflict = conflicts.some((c) => c.kind === 'industry_mismatch');
  const detectedCompany = primaryDetectedCompany(conflicts);

  return (
    <div
      className="mx-4 md:mx-6 mt-3 shrink-0 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      role="alert"
    >
      <p className="font-semibold text-amber-900">Engagement context mismatch</p>
      <p className="mt-1 text-amber-900/90">{conflictSummaryMessage(conflicts)}</p>
      <div className="mt-2 space-y-1 text-xs text-amber-800">
        {hasCompanyConflict ? (
          <p>
            Session company: <span className="font-medium">{engagementCompany ?? '—'}</span>
            {detectedCompany ? (
              <>
                {' '}
                · Upload suggests: <span className="font-medium">{detectedCompany}</span>
              </>
            ) : null}
          </p>
        ) : null}
        {hasIndustryConflict ? (
          <p>
            Session industry: <span className="font-medium">{engagementIndustry ?? '—'}</span>
            {detectedIndustryLabel ? (
              <>
                {' '}
                · Documents/spend suggest:{' '}
                <span className="font-medium">{detectedIndustryLabel}</span>
              </>
            ) : null}
          </p>
        ) : null}
        {manifest?.diagnostic_result ? (
          <p className="text-amber-700">(diagnostic context active)</p>
        ) : null}
      </div>
      {hasIndustryConflict ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <div className="w-full max-w-sm">
            <Select
              label="Sector pack for analysis"
              value={selectedSector}
              onChange={(e) => setSelectedSector(e.target.value)}
              disabled={resolving}
              options={[
                { value: '', label: 'Select sector pack…' },
                ...SECTOR_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
              ]}
            />
          </div>
          <button
            type="button"
            disabled={resolving || !selectedSector}
            onClick={() => void onApplySector(selectedSector)}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-900 text-white hover:bg-amber-950 disabled:opacity-50"
          >
            Apply sector pack
          </button>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        {detectedCompany && hasCompanyConflict ? (
          <button
            type="button"
            disabled={resolving}
            onClick={() => void onUseDetectedCompany(detectedCompany)}
            className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-900 text-white hover:bg-amber-950 disabled:opacity-50"
          >
            Use {detectedCompany} for this session
          </button>
        ) : null}
        <button
          type="button"
          disabled={resolving}
          onClick={onKeepEngagementCompany}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-amber-400 bg-white text-amber-900 hover:bg-amber-100 disabled:opacity-50"
        >
          Keep current context
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
        Analysis will still run, but benchmarks, sector levers, and deep-research context may not
        match uploaded spend until you align company and industry or replace the files.
      </p>
    </div>
  );
};
