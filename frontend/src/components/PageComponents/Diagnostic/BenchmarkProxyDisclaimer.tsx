import React from 'react';
import { Alert } from '../../Common/Alert';
import {
  BENCHMARK_PROXY_DISCLAIMER_RECOVERY,
  BENCHMARK_PROXY_DISCLAIMER_TITLE,
  benchmarkProxyDisclaimerDetail,
} from '../../../utils/diagnosticProxyDisclaimer';

interface BenchmarkProxyDisclaimerProps {
  dataNote?: string;
  /** Single-line banner for table cards */
  compact?: boolean;
  className?: string;
}

export const BenchmarkProxyDisclaimer: React.FC<BenchmarkProxyDisclaimerProps> = ({
  dataNote,
  compact = false,
  className = '',
}) => {
  const detail = benchmarkProxyDisclaimerDetail(dataNote);

  if (compact) {
    return (
      <p
        role="note"
        className={`text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 leading-relaxed ${className}`}
      >
        <span className="font-semibold">{BENCHMARK_PROXY_DISCLAIMER_TITLE}.</span>{' '}
        {detail}
      </p>
    );
  }

  return (
    <div className={className}>
      <Alert variant="warning" title={BENCHMARK_PROXY_DISCLAIMER_TITLE} recovery={BENCHMARK_PROXY_DISCLAIMER_RECOVERY}>
        {detail}
      </Alert>
    </div>
  );
};
