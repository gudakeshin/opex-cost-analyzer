import React from 'react';
import { STAGE_META } from './stageMeta';
import { stageLabel } from '../../../../utils/initiativeHelpers';

interface StageTagProps {
  stage: string;
}

export const StageTag: React.FC<StageTagProps> = ({ stage }) => {
  const m = STAGE_META[stage] ?? STAGE_META.identified;
  return (
    <span
      className="text-[11.5px] font-bold px-2 py-0.5 rounded-full border whitespace-nowrap"
      style={{ color: m.fg, background: m.bg, borderColor: m.bd }}
    >
      {m.label ?? stageLabel(stage)}
    </span>
  );
};
