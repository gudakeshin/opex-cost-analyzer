import React from 'react';
import { addressabilityScores } from '../../../utils/initiativeHelpers';
import type { Initiative } from '../../../types';

const DIMS = [
  { key: 'regulatory' as const, label: 'D' },
  { key: 'contract' as const, label: 'B' },
  { key: 'switching' as const, label: 'O' },
  { key: 'behaviour' as const, label: 'E' },
];

interface AddressabilityDotsProps {
  initiative: Initiative;
}

export const AddressabilityDots: React.FC<AddressabilityDotsProps> = ({ initiative }) => {
  const scores = addressabilityScores(initiative);
  return (
    <div
      className="flex gap-0.5"
      title="D·B·O·E·R — regulatory, contract window, switching cost, cost behaviour"
    >
      {DIMS.map(({ key, label }) => {
        const v = scores[key];
        const filled = v >= 0.65;
        return (
          <span
            key={key}
            className={`w-5 h-5 rounded text-[10px] font-semibold flex items-center justify-center border ${
              filled
                ? 'bg-brand-green/20 border-brand-green text-brand-navy'
                : 'bg-brand-surface-muted border-brand-border text-brand-muted'
            }`}
          >
            {label}
          </span>
        );
      })}
    </div>
  );
};
