import React, { useMemo } from 'react';
import { currencySymbol } from '../../../utils/currencySymbol';
import { SignalChip } from './primitives/SignalChip';
import { getAqs, isNeedsActionInitiative } from '../../../utils/initiativeHelpers';
import type { Initiative } from '../../../types';
import { toCr } from '../../../utils/formatInr';

interface SignalStripProps {
  initiatives: Initiative[];
  currency?: string;
  realizedCr?: number;
  onNeedsActionClick?: () => void;
}

export const SignalStrip: React.FC<SignalStripProps> = ({
  initiatives,
  currency = 'INR',
  realizedCr,
  onNeedsActionClick,
}) => {
  const live = useMemo(
    () => initiatives.filter((x) => x.stage !== 'rejected' && x.stage !== 'deferred'),
    [initiatives],
  );
  const needsAction = useMemo(() => live.filter(isNeedsActionInitiative).length, [live]);
  const avgAqs = useMemo(() => {
    if (live.length === 0) return 0;
    const sum = live.reduce((s, x) => s + (getAqs(x) ?? 0.72), 0);
    return Math.round((sum / live.length) * 100);
  }, [live]);
  const realized = useMemo(() => {
    if (realizedCr != null) return realizedCr;
    return live
      .filter((x) => x.stage === 'realized')
      .reduce((s, x) => s + toCr(x.gross_savings_y1 ?? 0, currency), 0);
  }, [live, realizedCr, currency]);

  const sym = currencySymbol(currency);

  return (
    <div className="flex flex-wrap gap-2.5">
      <SignalChip value={live.length} label="Live initiatives" />
      <SignalChip
        value={needsAction}
        label="Need action now"
        highlight={needsAction > 0}
        onClick={onNeedsActionClick}
      />
      <SignalChip value={`${avgAqs}%`} label="Avg assumption quality" />
      <SignalChip
        value={
          <span className="cr-mono">
            {sym}
            {realized.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </span>
        }
        label="Realised to date (Cr)"
      />
    </div>
  );
};
