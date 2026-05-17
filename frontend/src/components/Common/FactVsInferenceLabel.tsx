import React from 'react';

type Kind = 'fact' | 'inference';

interface FactVsInferenceLabelProps {
  kind: Kind;
  className?: string;
}

export const FactVsInferenceLabel: React.FC<FactVsInferenceLabelProps> = ({
  kind,
  className = '',
}) => (
  <span
    className={`inline-flex items-center text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border-l-4 ${
      kind === 'fact'
        ? 'border-brand-navy text-brand-navy bg-brand-navy/5'
        : 'border-brand-green text-brand-green bg-brand-green/10'
    } ${className}`}
  >
    {kind === 'fact' ? 'Fact' : 'AI inference'}
  </span>
);
