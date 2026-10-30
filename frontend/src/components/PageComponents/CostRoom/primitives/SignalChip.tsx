import React from 'react';

interface SignalChipProps {
  value: React.ReactNode;
  label: string;
  highlight?: boolean;
  onClick?: () => void;
}

export const SignalChip: React.FC<SignalChipProps> = ({
  value,
  label,
  highlight = false,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={!onClick}
    className={`flex items-center gap-2 bg-white border rounded-[var(--cr-r)] px-4 py-3 flex-1 min-w-[150px] shadow-sm text-left transition-colors ${
      highlight
        ? 'border-[#f0dcb0] bg-[var(--cr-amber-soft)]'
        : 'border-[var(--cr-line)]'
    } ${onClick ? 'cursor-pointer hover:border-[var(--cr-green)]' : 'cursor-default'}`}
  >
    <div>
      <div
        className={`text-lg font-extrabold tabular-nums ${
          highlight ? 'text-[var(--cr-amber)]' : 'text-[var(--cr-ink)]'
        }`}
      >
        {value}
      </div>
      <div className="text-[11.5px] text-[var(--cr-gray-2)] font-semibold">{label}</div>
    </div>
  </button>
);
