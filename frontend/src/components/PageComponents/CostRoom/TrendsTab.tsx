import React from 'react';
import { Loader } from '../../Common/Loader';

interface TrendsTabProps {
  data: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
}

export const TrendsTab: React.FC<TrendsTabProps> = ({ data, loading, error }) => {
  if (loading) return <Loader label="Loading trends…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-gray-500 text-sm">Run analysis with a session to view trends.</p>;
  return (
    <pre className="text-xs font-mono overflow-auto max-h-96 p-4 bg-gray-50 dark:bg-gray-900 rounded">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
};
