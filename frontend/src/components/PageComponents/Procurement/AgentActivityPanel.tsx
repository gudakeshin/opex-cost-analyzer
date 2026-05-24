import React from 'react';
import { Loader } from '../../Common/Loader';
import { LogicTrace } from '../../Trust/LogicTrace';
import type { ProgressStep } from '../../../types';

interface AgentActivityPanelProps {
  steps?: ProgressStep[];
  runId?: string;
  loading?: boolean;
  degradedMode?: boolean;
  pipelineLabel?: string;
}

export const AgentActivityPanel: React.FC<AgentActivityPanelProps> = ({
  steps,
  runId,
  loading,
  degradedMode,
  pipelineLabel,
}) => (
  <div>
    <p className="text-xs font-semibold uppercase text-brand-muted mb-2">Agent activity</p>
    {pipelineLabel && (
      <p className="text-xs text-brand-muted mb-2 font-mono">{pipelineLabel}</p>
    )}
    {loading && !steps?.length ? (
      <div className="flex items-center gap-2 text-sm text-brand-muted">
        <Loader label="" />
        <span>OPAR agent running…</span>
      </div>
    ) : (
      <LogicTrace steps={steps} runId={runId} degradedMode={degradedMode} />
    )}
  </div>
);
