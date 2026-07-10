import { describe, expect, it } from 'vitest';
import type { PeerRow } from '../types/sectorPack';
import {
  activePeerSizeColumns,
  peerSizeColumnHeader,
  peerSizeValue,
} from './peerSizeFields';

describe('peerSizeFields', () => {
  it('detects group_revenue_cr column for conglomerate peers', () => {
    const peers: PeerRow[] = [{ name: 'Tata', group_revenue_cr: 1400000 }];
    expect(activePeerSizeColumns(peers)).toEqual([
      { key: 'group_revenue_cr', header: 'Group revenue (Cr)' },
    ]);
    expect(peerSizeColumnHeader(peers)).toBe('Group revenue (Cr)');
    expect(peerSizeValue(peers[0])).toBe(1400000);
  });

  it('detects total_assets_cr column for bank peers', () => {
    const peers: PeerRow[] = [{ name: 'SBI', total_assets_cr: 6200000 }];
    expect(activePeerSizeColumns(peers)).toEqual([
      { key: 'total_assets_cr', header: 'Total assets (Cr)' },
    ]);
    expect(peerSizeValue(peers[0])).toBe(6200000);
  });

  it('defaults to revenue_cr when peers have no size field', () => {
    expect(activePeerSizeColumns([{ name: 'New peer' }])).toEqual([
      { key: 'revenue_cr', header: 'Revenue (Cr)' },
    ]);
  });
});
