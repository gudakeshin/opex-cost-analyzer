import React from 'react';
import { collectTopProbeQuestions, formatSpendAmount } from '../../../utils/analysisInsights';
import type { AnalysisInsightSnapshot } from '../../../types';

interface ProbeQuestionsBlockProps {
  snapshot: AnalysisInsightSnapshot;
  currency: string;
  onAnswer?: (message: string) => void;
}

export const ProbeQuestionsBlock: React.FC<ProbeQuestionsBlockProps> = ({
  snapshot,
  currency,
  onAnswer,
}) => {
  const probes = collectTopProbeQuestions(snapshot, 5);
  if (probes.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-brand-border space-y-2">
      <p className="text-[10px] font-semibold uppercase text-brand-muted">Probe questions</p>
      <ol className="list-decimal list-inside space-y-2 text-xs text-brand-ink leading-snug">
        {probes.map((p) => (
          <li key={p.question} className="break-words">
            <span className="font-medium">{p.category_name}</span>
            {' — '}
            {p.question}
            {p.saving_at_stake > 0 && (
              <span className="text-brand-muted">
                {' '}
                ({formatSpendAmount(p.saving_at_stake, currency)} at stake)
              </span>
            )}
          </li>
        ))}
      </ol>
      {onAnswer && (
        <div className="flex flex-wrap gap-2">
          {probes.slice(0, 3).map((p) => (
            <button
              key={p.question}
              type="button"
              onClick={() => onAnswer(p.question)}
              className="text-xs px-3 py-1.5 rounded-full border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 text-left max-w-full break-words"
            >
              Answer: {p.category_name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
