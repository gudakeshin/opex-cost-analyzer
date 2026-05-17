import React from 'react';

type AlertVariant = 'error' | 'warning' | 'info' | 'success';

interface AlertProps {
  variant?: AlertVariant;
  title: string;
  children?: React.ReactNode;
  recovery?: string;
  onDismiss?: () => void;
}

const styles: Record<AlertVariant, string> = {
  error: 'bg-red-50 border-red-200 text-red-900',
  warning: 'bg-amber-50 border-amber-200 text-amber-900',
  info: 'bg-blue-50 border-blue-200 text-blue-900',
  success: 'bg-green-50 border-green-200 text-green-900',
};

export const Alert: React.FC<AlertProps> = ({
  variant = 'error',
  title,
  children,
  recovery,
  onDismiss,
}) => (
  <div role="alert" className={`p-4 rounded-xl border text-sm ${styles[variant]}`}>
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="font-semibold">{title}</p>
        {children && <p className="mt-1 opacity-90">{children}</p>}
        {recovery && <p className="mt-2 text-xs font-medium opacity-80">Next step: {recovery}</p>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 p-1 rounded hover:bg-black/5"
          aria-label="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  </div>
);
