import React, { useId } from 'react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  /** Helper text shown under the field and linked via aria-describedby. */
  hint?: string;
  /** Validation message; marks the field invalid and is announced to screen readers. */
  error?: string;
}

export const Input: React.FC<InputProps> = ({ label, hint, error, className = '', id, ...props }) => {
  const autoId = useId();
  const inputId = id || autoId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [props['aria-describedby'], hintId, errorId].filter(Boolean).join(' ') || undefined;
  return (
    <div>
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-brand-ink mb-2">
          {label}
        </label>
      )}
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`w-full px-4 py-2 border rounded-lg bg-white text-brand-ink text-sm font-sans ${
          error ? 'border-error' : 'border-brand-border'
        } ${className}`}
        {...props}
      />
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
