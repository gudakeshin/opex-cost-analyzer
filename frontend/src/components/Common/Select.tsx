import React, { useId } from 'react';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: Array<{ value: string; label: string }>;
  hint?: string;
  error?: string;
}

export const Select: React.FC<SelectProps> = ({ label, options, hint, error, className = '', id, ...props }) => {
  const autoId = useId();
  const selectId = id || autoId;
  const hintId = hint ? `${selectId}-hint` : undefined;
  const errorId = error ? `${selectId}-error` : undefined;
  const describedBy = [props['aria-describedby'], hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div>
      {label && (
        <label htmlFor={selectId} className="block text-sm font-medium text-brand-ink mb-2">
          {label}
        </label>
      )}
      <select
        id={selectId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`w-full px-4 py-2 border rounded-lg bg-white text-brand-ink text-sm font-sans ${
          error ? 'border-error' : 'border-brand-border'
        } ${className}`}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hint && (
        <p id={hintId} className="mt-1 text-xs text-brand-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="mt-1 text-xs text-error">
          {error}
        </p>
      )}
    </div>
  );
};
