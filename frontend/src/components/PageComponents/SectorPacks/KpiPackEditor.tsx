import React from 'react';
import type { KpiRow } from '../../../types/sectorPack';
import { TARGET_DIRECTION_OPTIONS } from '../../../types/sectorPack';
import { EditableTable } from './EditableTable';

interface KpiPackEditorProps {
  draft: KpiRow[];
  onChange: (draft: KpiRow[]) => void;
}

export const KpiPackEditor: React.FC<KpiPackEditorProps> = ({ draft, onChange }) => (
  <EditableTable<KpiRow>
    columns={[
      { key: 'kpi_id', header: 'KPI ID', minWidth: '10rem' },
      { key: 'kpi_name', header: 'Name', minWidth: '12rem' },
      { key: 'unit', header: 'Unit' },
      { key: 'formula', header: 'Formula', type: 'textarea', minWidth: '14rem' },
      { key: 'target_direction', header: 'Target', type: 'select', options: TARGET_DIRECTION_OPTIONS },
      { key: 'p50_benchmark_pct', header: 'P50 %', type: 'number' },
      { key: 'p50_benchmark_cr', header: 'P50 Cr', type: 'number' },
      { key: 'p50_benchmark_inr', header: 'P50 INR', type: 'number' },
    ]}
    rows={draft}
    onChange={onChange}
    newRow={() => ({ kpi_id: '', kpi_name: '', unit: 'pct', target_direction: 'lower' })}
    rowKey={(row) => String(row.kpi_id || Math.random())}
    emptyMessage="No KPIs defined. Add a row to start."
  />
);
