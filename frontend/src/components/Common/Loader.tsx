import React from 'react';

interface LoaderProps {
  label?: string;
}

export const Loader: React.FC<LoaderProps> = ({ label = 'Loading…' }) => (
  <div className="flex flex-col items-center justify-center py-8">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-deloitte-green" />
    <p className="mt-4 text-gray-600 dark:text-gray-400 text-sm">{label}</p>
  </div>
);
