import React from 'react';
import { ConfidenceBadge } from '../../Trust/ConfidenceBadge';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';

interface FindingCardsProps {
  findings: string[];
}

export const FindingCards: React.FC<FindingCardsProps> = ({ findings }) => {
  if (!findings.length) return null;

  return (
    <div className="space-y-3">
      {findings.map((text, i) => {
        const confidence = i === 0 ? 0.82 : i < 3 ? 0.72 : 0.65;
        return (
          <article
            key={i}
            className="p-4 rounded-xl border border-brand-border bg-white border-l-4 border-l-brand-green"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <FactVsInferenceLabel kind="inference" />
              <ConfidenceBadge signals={{ faithfulness_score: confidence }} compact />
            </div>
            <p className="text-sm text-brand-ink">{text}</p>
            <p className="text-xs text-brand-muted mt-2">Rank #{i + 1} by materiality</p>
          </article>
        );
      })}
    </div>
  );
};
