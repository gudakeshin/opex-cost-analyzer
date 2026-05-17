import React from 'react';

type Tone = 'default' | 'success' | 'warning' | 'error';

const tones: Record<Tone, string> = {
  default: 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200',
  success: 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200',
  warning: 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200',
  error: 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200',
};

interface BadgeProps {
  children: React.ReactNode;
  tone?: Tone;
}

export const Badge: React.FC<BadgeProps> = ({ children, tone = 'default' }) => (
  <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${tones[tone]}`}>
    {children}
  </span>
);
