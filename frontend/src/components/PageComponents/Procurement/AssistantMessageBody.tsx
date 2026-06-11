import React from 'react';
import { Markdown } from '../../Common/Markdown';
import { CategoryInsightCard } from './CategoryInsightCard';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { AssistantPayload, CategoryInsightData, PresentationBlock } from '../../../types';

interface AssistantMessageBodyProps {
  presentation: AssistantPayload;
  currency?: string;
}

function renderBlock(block: PresentationBlock, currency: string, key: string) {
  switch (block.kind) {
    case 'metric_strip': {
      const total = block.data.total_spend as number | undefined;
      const count = block.data.category_count as number | undefined;
      if (!total) return null;
      return (
        <div key={key} className="rounded-lg border border-brand-border px-3 py-2 text-[11px] flex justify-between gap-3">
          <span className="text-brand-muted uppercase font-semibold tracking-wide">{block.title || 'Portfolio'}</span>
          <span className="font-medium tabular-nums">
            {formatSpendAmount(total, currency)}
            {count != null ? ` · ${count} categories` : ''}
          </span>
        </div>
      );
    }
    case 'category_insight':
      return (
        <CategoryInsightCard
          key={key}
          data={block.data as unknown as CategoryInsightData}
          currency={currency}
        />
      );
    case 'quick_wins':
    case 'callout_list': {
      const items = (block.data.items as string[]) || [];
      if (!items.length) return null;
      return (
        <div key={key}>
          <p className="text-xs font-bold uppercase text-brand-muted mb-1">{block.title}</p>
          <ul className="text-xs list-disc list-inside space-y-0.5">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      );
    }
    case 'lever_list': {
      const levers = (block.data.levers as Array<Record<string, unknown>>) || [];
      if (!levers.length) return null;
      return (
        <div key={key}>
          <p className="text-xs font-bold uppercase text-brand-muted mb-1">{block.title}</p>
          <ul className="text-xs space-y-2">
            {levers.map((lv, i) => (
              <li key={String(lv.lever_name ?? i)} className="border-l-2 border-deloitte-green pl-2">
                <span className="font-semibold">{String(lv.lever_name ?? 'Lever')}</span>
                {lv.what_changes ? (
                  <p className="text-brand-muted mt-0.5">{String(lv.what_changes)}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case 'action_timeline': {
      const actions = (block.data.actions as Array<Record<string, unknown>>) || [];
      if (!actions.length) return null;
      return (
        <div key={key}>
          <p className="text-xs font-bold uppercase text-brand-muted mb-1">{block.title}</p>
          <ul className="text-xs space-y-1.5">
            {actions.map((a, i) => (
              <li key={i}>
                <span className="font-semibold text-brand-navy">{String(a.timeline ?? '')}</span>
                {' — '}
                {String(a.action ?? '')}
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case 'markdown_narrative': {
      const md = String(block.data.markdown ?? '');
      if (!md.trim()) return null;
      const isCausal = block.data.variant === 'causal_prose';
      return (
        <div
          key={key}
          className={
            isCausal
              ? 'rounded-lg border border-brand-border bg-brand-surface-muted/30 px-3 py-2.5 space-y-1'
              : undefined
          }
        >
          {block.title ? (
            <p
              className={
                isCausal
                  ? 'text-xs font-bold text-brand-navy mb-2'
                  : 'text-xs font-bold uppercase text-brand-muted mb-1'
              }
            >
              {block.title}
            </p>
          ) : null}
          <Markdown className={isCausal ? 'text-sm leading-relaxed' : 'text-xs leading-relaxed'}>
            {md}
          </Markdown>
        </div>
      );
    }
    default:
      return null;
  }
}

export const AssistantMessageBody: React.FC<AssistantMessageBodyProps> = ({
  presentation,
  currency = 'INR',
}) => {
  const narrative = (presentation.narrative_markdown || '').trim();
  const blocks = presentation.blocks || [];

  return (
    <div className="space-y-3">
      {narrative ? (
        <Markdown className="text-sm leading-relaxed">{narrative}</Markdown>
      ) : null}
      {blocks.map((block, i) => renderBlock(block, currency, `${block.kind}-${i}`))}
    </div>
  );
};
