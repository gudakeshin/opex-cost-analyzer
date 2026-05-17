import React from 'react';
import { Card } from './Card';

interface MetricTileProps {
  label: string;
  value: string;
  change?: string;
  highlight?: boolean;
}

export const MetricTile: React.FC<MetricTileProps> = ({ label, value, change, highlight }) => (
  <Card className="!p-4 bg-white border-brand-border">
    <p className="text-brand-muted text-sm">{label}</p>
    <p
      className={`text-2xl font-bold mt-1 tabular-nums ${
        highlight ? 'text-brand-navy' : 'text-brand-ink'
      }`}
    >
      {value}
    </p>
    {change && <p className="text-xs mt-2 text-brand-green font-medium">{change}</p>}
  </Card>
);
