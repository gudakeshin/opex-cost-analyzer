import React from 'react';

type Kind = 'fact' | 'inference' | 'benchmark_proxy';

interface FactVsInferenceLabelProps {
  kind: Kind;
  className?: string;
}

const KIND_STYLES: Record<Kind, string> = {
  fact: 'border-brand-navy text-brand-navy bg-brand-navy/5',
  inference: 'border-brand-green text-brand-green bg-brand-green/10',
  benchmark_proxy: 'border-amber-500 text-amber-900 bg-amber-50',
};

const KIND_LABELS: Record<Kind, string> = {
  fact: 'Fact',
  inference: 'AI inference',
  benchmark_proxy: 'Benchmark proxy',
};

export const FactVsInferenceLabel: React.FC<FactVsInferenceLabelProps> = ({
  kind,
  className = '',
}) => (
  <span
    className={`inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border-l-4 ${KIND_STYLES[kind]} ${className}`}
  >
    {KIND_LABELS[kind]}
  </span>
);
