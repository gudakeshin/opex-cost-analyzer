import React from 'react';
import { Table, Column } from '../../Common/Table';
import { AqsBadge } from './AqsBadge';
import { AddressabilityDots } from './AddressabilityDots';
import { InitiativeRowActions } from './InitiativeRowActions';
import { formatBandRange, formatBps, formatCr } from '../../../utils/formatInr';
import { getAqs, getBandSavings, stageLabel } from '../../../utils/initiativeHelpers';
import type { Initiative, PercentileBand } from '../../../types';

interface InitiativePortfolioProps {
  initiatives: Initiative[];
  percentileBand: PercentileBand;
  executive?: boolean;
  currency?: string;
  onSelect: (init: Initiative) => void;
  acceptInit: (id: string) => void;
  deferInit: (id: string) => void;
  rejectInit: (id: string) => void;
}

export const InitiativePortfolio: React.FC<InitiativePortfolioProps> = ({
  initiatives,
  percentileBand,
  executive = true,
  currency = 'USD',
  onSelect,
  acceptInit,
  deferInit,
  rejectInit,
}) => {
  const sym = currency === 'INR' ? '₹' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '$';
  const unit = currency === 'INR' ? 'Cr' : 'M';
  const columns: Column<Initiative>[] = [
    {
      key: 'index',
      header: '#',
      render: (_, i) => <span className="text-brand-muted tabular-nums">{String(i! + 1).padStart(2, '0')}</span>,
    },
    {
      key: 'initiative',
      header: 'Initiative',
      render: (r) => (
        <div className="min-w-[200px]">
          <p className="font-medium text-brand-ink">{r.lever || r.category}</p>
          {r.description && (
            <p className="text-xs text-brand-muted mt-0.5 line-clamp-2">{String(r.description)}</p>
          )}
          {r.root_cause && !r.description && (
            <p className="text-xs text-brand-muted mt-0.5 line-clamp-2">{r.root_cause}</p>
          )}
        </div>
      ),
    },
    {
      key: 'pool',
      header: executive ? 'Pool' : 'Category',
      render: (r) => r.category,
    },
    ...(executive
      ? [
          {
            key: 'owner',
            header: 'Owner',
            render: (r: Initiative) => r.owner_name || '—',
          } as Column<Initiative>,
        ]
      : []),
    {
      key: 'p50',
      header: `P50 ${sym}${unit}`,
      render: (r) => {
        const p50 = getBandSavings(r, 'p50');
        const perYear = r.savings_type === 'run_rate' || !r.savings_type;
        return (
          <span className="font-mono tabular-nums font-semibold">
            {formatCr(p50, { perYear, decimals: 0, currency }).replace(` ${unit}`, '')}
          </span>
        );
      },
    },
    {
      key: 'band',
      header: 'P10 → P90',
      render: (r) => (
        <span className="text-sm tabular-nums text-brand-muted">
          {formatBandRange(getBandSavings(r, 'p10'), getBandSavings(r, 'p90'))}
        </span>
      ),
    },
    ...(executive
      ? [
          {
            key: 'bps',
            header: 'bps EB',
            render: (r: Initiative) => {
              const bps = Number(r.ebitda_bps ?? (getBandSavings(r, 'p50') / 2500) * 100);
              return formatBps(bps);
            },
          } as Column<Initiative>,
        ]
      : [
          {
            key: 'net_npv',
            header: `NPV (${percentileBand})`,
            render: (r: Initiative) => {
              const base = getBandSavings(r, percentileBand);
              return base.toLocaleString('en-IN', { maximumFractionDigits: 0 });
            },
          } as Column<Initiative>,
        ]),
    {
      key: 'aqs',
      header: (
        <span className="inline-flex items-center gap-1">
          AQS
          <span
            className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-gray-100 text-gray-500 text-[9px] font-bold cursor-help leading-none"
            title="Assumption Quality Score — measures how well each savings assumption is supported by data. Gate-2 requires ≥65% to commit. Green (Strong) ≥80%, Amber (Gate pass) 65–79%, Red (Blocked) <65%. A low AQS means more data or validation is needed before committing."
          >
            ?
          </span>
        </span>
      ),
      render: (r) => <AqsBadge score={getAqs(r)} />,
    },
    ...(executive
      ? [
          {
            key: 'sust',
            header: 'Sust.',
            render: (r: Initiative) => {
              const s = r.sustainability_score;
              if (s == null) return 'N/A';
              return Number(s).toFixed(2);
            },
          } as Column<Initiative>,
          {
            key: 'bounce',
            header: 'B-back',
            render: (r: Initiative) => r.bounce_back_risk ?? 'N/A',
          } as Column<Initiative>,
          {
            key: 'type',
            header: 'Type',
            render: (r: Initiative) => r.savings_type ?? 'run_rate',
          } as Column<Initiative>,
          {
            key: 'dber',
            header: 'D·B·O·E·R',
            render: (r: Initiative) => <AddressabilityDots initiative={r} />,
          } as Column<Initiative>,
        ]
      : []),
    {
      key: 'status',
      header: 'Status',
      render: (r) => (
        <span className="text-sm">{stageLabel(r.stage)}</span>
      ),
    },
    {
      key: 'actions',
      header: executive ? 'Action' : 'Actions',
      render: (r) => (
        <InitiativeRowActions
          initiative={r}
          onView={() => onSelect(r)}
          onAccept={acceptInit}
          onDefer={deferInit}
          onReject={rejectInit}
        />
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      data={initiatives}
      keyField="initiative_id"
      emptyMessage="No initiatives in pipeline. Run analysis first, then open the Cost Room."
    />
  );
};
