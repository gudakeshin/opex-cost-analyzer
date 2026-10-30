import type { PeerRow } from '../types/sectorPack';

export const PEER_SIZE_FIELDS = [
  { key: 'revenue_cr', header: 'Revenue (Cr)' },
  { key: 'group_revenue_cr', header: 'Group revenue (Cr)' },
  { key: 'total_assets_cr', header: 'Total assets (Cr)' },
  { key: 'gwp_cr', header: 'GWP (Cr)' },
] as const satisfies ReadonlyArray<{ key: keyof PeerRow; header: string }>;

export type PeerSizeFieldKey = (typeof PEER_SIZE_FIELDS)[number]['key'];

function hasPeerSizeValue(peer: PeerRow, key: PeerSizeFieldKey): boolean {
  return peer[key] != null;
}

export function activePeerSizeColumns(
  peers: PeerRow[],
): ReadonlyArray<{ key: PeerSizeFieldKey; header: string }> {
  const used = PEER_SIZE_FIELDS.filter(({ key }) => peers.some((p) => hasPeerSizeValue(p, key)));
  return used.length > 0 ? used : [PEER_SIZE_FIELDS[0]];
}

export function peerSizeColumnHeader(peers: PeerRow[]): string {
  const columns = activePeerSizeColumns(peers);
  if (columns.length === 1) return columns[0].header;
  return 'Size (Cr)';
}

export function peerSizeValue(peer: PeerRow): number | undefined {
  for (const { key } of PEER_SIZE_FIELDS) {
    const value = peer[key];
    if (value != null) return value;
  }
  return undefined;
}
