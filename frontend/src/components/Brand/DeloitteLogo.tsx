import React from 'react';

interface DeloitteLogoProps {
  variant?: 'full' | 'mark';
  className?: string;
  light?: boolean;
}

/**
 * Deloitte wordmark — black type + green dot, aligned with
 * https://www.deloitte.com/in/en/issues/digital.html
 */
export const DeloitteLogo: React.FC<DeloitteLogoProps> = ({
  variant = 'full',
  className = '',
  light = false,
}) => {
  const textClass = light ? 'text-white' : 'text-black';

  if (variant === 'mark') {
    return (
      <span
        className={`inline-flex items-center justify-center w-8 h-8 ${className}`}
        aria-label="Deloitte"
      >
        <span className="text-xl font-bold leading-none text-deloitte-green">.</span>
      </span>
    );
  }

  return (
    <span className={`inline-flex items-baseline gap-0 ${className}`} aria-label="Deloitte">
      <span className={`font-semibold text-[15px] tracking-tight ${textClass}`}>Deloitte</span>
      <span className="text-[15px] font-bold leading-none text-deloitte-green">.</span>
    </span>
  );
};
