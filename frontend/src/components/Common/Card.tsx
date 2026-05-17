import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
}

export const Card: React.FC<CardProps> = ({ children, className = '', title }) => (
  <div className={`bg-white rounded-lg border border-brand-border shadow-sm ${className}`}>
    {title && (
      <div className="px-6 py-4 border-b border-brand-border">
        <h3 className="text-sm font-semibold text-brand-ink">{title}</h3>
      </div>
    )}
    <div className="p-6">{children}</div>
  </div>
);
