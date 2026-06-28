import React from 'react';

interface ConfidenceBandTrackProps {
  band: 'p10' | 'p50' | 'p90';
  tipLabel: string;
  p10Label: string;
  p50Label: string;
  p90Label: string;
}

export const ConfidenceBandTrack: React.FC<ConfidenceBandTrackProps> = ({
  band,
  tipLabel,
  p10Label,
  p50Label,
  p90Label,
}) => {
  const left = band === 'p10' ? 12 : band === 'p90' ? 88 : 50;
  return (
    <div className="relative mt-6 mx-1 mb-2">
      <div className="relative h-2 rounded-md bg-gradient-to-r from-[var(--cr-line)] via-[#cfe39f] to-[var(--cr-green)]">
        <div
          className="absolute top-1/2 w-4 h-4 rounded-full bg-white border-[3px] border-[var(--cr-ink)] -translate-x-1/2 -translate-y-1/2 shadow-sm transition-[left] duration-300"
          style={{ left: `${left}%` }}
        />
        <div
          className="absolute bottom-4 -translate-x-1/2 text-[11px] font-bold bg-[var(--cr-ink)] text-white px-1.5 py-0.5 rounded whitespace-nowrap transition-[left] duration-300 after:content-[''] after:absolute after:top-full after:left-1/2 after:-translate-x-1/2 after:border-4 after:border-transparent after:border-t-[var(--cr-ink)]"
          style={{ left: `${left}%` }}
        >
          {tipLabel}
        </div>
      </div>
      <div className="flex justify-between text-[11px] text-[var(--cr-gray-2)] cr-mono mt-2">
        <span>P10 {p10Label}</span>
        <span>P50 {p50Label}</span>
        <span>P90 {p90Label}</span>
      </div>
    </div>
  );
};
