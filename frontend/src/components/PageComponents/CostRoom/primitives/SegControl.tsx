export interface SegOption<T extends string> {
  value: T;
  label: string;
}

interface SegControlProps<T extends string> {
  value: T;
  options: SegOption<T>[];
  onChange: (value: T) => void;
  green?: boolean;
  className?: string;
}

export function SegControl<T extends string>({
  value,
  options,
  onChange,
  green = false,
  className = '',
}: SegControlProps<T>) {
  return (
    <div
      className={`inline-flex bg-[var(--cr-muted)] border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] p-0.5 gap-0.5 ${className}`}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`font-semibold text-xs px-2.5 py-1 rounded-[5px] whitespace-nowrap transition-colors ${
            value === o.value
              ? green
                ? 'bg-[var(--cr-green)] text-white shadow-sm'
                : 'bg-white text-[var(--cr-ink)] shadow-sm'
              : 'bg-transparent text-[var(--cr-gray)] hover:text-[var(--cr-ink)]'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
