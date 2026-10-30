import React, { useMemo } from 'react';
import type { PeerMetricDraftRow, PeerRow, PeersDraft } from '../../../types/sectorPack';
import { activePeerSizeColumns } from '../../../utils/peerSizeFields';
import { EditableTable, type EditableColumnDef } from './EditableTable';

interface PeersEditorProps {
  draft: PeersDraft;
  onChange: (draft: PeersDraft) => void;
}

export const PeersEditor: React.FC<PeersEditorProps> = ({ draft, onChange }) => {
  const peerColumns = useMemo((): EditableColumnDef<PeerRow>[] => {
    const base: EditableColumnDef<PeerRow>[] = [
      { key: 'name', header: 'Name', minWidth: '12rem' },
      { key: 'ticker', header: 'Ticker' },
      { key: 'exchange', header: 'Exchange' },
      { key: 'entity_type', header: 'Entity type' },
    ];
    const sizeColumns = activePeerSizeColumns(draft.peers).map(({ key, header }) => ({
      key,
      header,
      type: 'number' as const,
    }));
    return [...base, ...sizeColumns];
  }, [draft.peers]);

  return (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
      {(['sector', 'currency', 'data_source', 'refresh_date'] as const).map((key) => (
        <label key={key} className="block">
          <span className="text-xs text-brand-muted">{key.replace(/_/g, ' ')}</span>
          <input
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm"
            value={draft[key]}
            onChange={(e) => onChange({ ...draft, [key]: e.target.value })}
          />
        </label>
      ))}
    </div>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Peers</h3>
      <EditableTable<PeerRow>
        columns={peerColumns}
        rows={draft.peers}
        onChange={(peers) => onChange({ ...draft, peers })}
        newRow={() => ({ name: '', ticker: '' })}
        rowKey={(row) => String(row.ticker || row.name || Math.random())}
      />
    </section>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Benchmark metrics</h3>
      <EditableTable<PeerMetricDraftRow>
        columns={[
          { key: 'key', header: 'Metric key', minWidth: '14rem' },
          { key: 'p25', header: 'P25', type: 'number' },
          { key: 'p50', header: 'P50', type: 'number' },
          { key: 'p75', header: 'P75', type: 'number' },
        ]}
        rows={draft.benchmark_metrics}
        onChange={(benchmark_metrics) => onChange({ ...draft, benchmark_metrics })}
        newRow={() => ({ key: '' })}
        rowKey={(row) => row.key || String(Math.random())}
      />
    </section>
  </div>
  );
};
