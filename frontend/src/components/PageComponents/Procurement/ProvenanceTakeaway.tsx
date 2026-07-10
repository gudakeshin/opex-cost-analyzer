import React, { useEffect, useState } from 'react';
import { apiGet } from '../../../hooks/useApi';
import { Markdown } from '../../Common/Markdown';

export interface ProvenanceSentenceRecord {
  sentence: string;
  provenance?: {
    data_slice?: string[];
    model_version?: string;
    prompt_hash?: string;
  };
}

interface ProvenanceSnapshotResponse {
  sentences: ProvenanceSentenceRecord[];
}

function formatSkillsTooltip(skills: string[]): string {
  if (skills.length === 0) return 'See Provenance tab for sources';
  return `Grounded in: ${skills.join(', ')}`;
}

function ProvenanceSentenceSpan({ record }: { record: ProvenanceSentenceRecord }) {
  const skills = record.provenance?.data_slice ?? [];
  const tip = formatSkillsTooltip(skills);
  return (
    <span
      className={
        skills.length > 0
          ? 'border-b border-dotted border-slate-400 cursor-help hover:bg-slate-50 rounded-sm'
          : undefined
      }
      title={tip}
    >
      {record.sentence}{' '}
    </span>
  );
}

export const ProvenanceTakeaway: React.FC<{
  text: string;
  engagementId?: string;
  turnId?: string;
}> = ({ text, engagementId, turnId }) => {
  const [records, setRecords] = useState<ProvenanceSentenceRecord[] | null>(null);

  useEffect(() => {
    if (!engagementId || !turnId || !text.trim()) {
      setRecords(null);
      return;
    }
    let cancelled = false;
    apiGet<ProvenanceSnapshotResponse>(
      `/api/v1/provenance/${encodeURIComponent(engagementId)}/${encodeURIComponent(turnId)}`,
    )
      .then((res) => {
        if (!cancelled) setRecords(res.sentences ?? []);
      })
      .catch(() => {
        if (!cancelled) setRecords(null);
      });
    return () => {
      cancelled = true;
    };
  }, [engagementId, turnId, text]);

  if (!records?.length) {
    return <Markdown className="text-xs leading-relaxed">{text}</Markdown>;
  }

  return (
    <p className="text-xs leading-relaxed">
      {records.map((rec, i) => (
        <ProvenanceSentenceSpan key={`${i}-${rec.sentence.slice(0, 24)}`} record={rec} />
      ))}
    </p>
  );
};
