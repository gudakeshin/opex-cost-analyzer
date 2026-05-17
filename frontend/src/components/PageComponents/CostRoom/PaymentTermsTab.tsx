import React from 'react';
import { Loader } from '../../Common/Loader';

interface PaymentTermsTabProps {
  data: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
}

export const PaymentTermsTab: React.FC<PaymentTermsTabProps> = ({ data, loading, error }) => {
  if (loading) return <Loader label="Loading payment terms…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-gray-500 text-sm">No payment terms analysis for this session.</p>;
  return (
    <pre className="text-xs font-mono overflow-auto max-h-96 p-4 bg-gray-50 dark:bg-gray-900 rounded">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
};
