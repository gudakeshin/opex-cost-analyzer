export const STAGE_META: Record<
  string,
  { label: string; fg: string; bg: string; bd: string }
> = {
  identified: { label: 'Pending', fg: '#75787B', bg: '#F1F1EE', bd: '#E4E4E1' },
  proposed: { label: 'Proposed', fg: '#16324F', bg: '#E5ECF3', bd: '#c9d8e6' },
  validated: { label: 'Validated', fg: '#2f6a1e', bg: '#EAF4D7', bd: '#cfe39f' },
  committed: { label: 'Committed', fg: '#fff', bg: '#86BC25', bd: '#86BC25' },
  in_flight: { label: 'In-flight', fg: '#fff', bg: '#16324F', bd: '#16324F' },
  realized: { label: 'Realized', fg: '#fff', bg: '#5C8A0A', bd: '#5C8A0A' },
  deferred: { label: 'Deferred', fg: '#C97A12', bg: '#FBEFD8', bd: '#f0dcb0' },
  rejected: { label: 'Rejected', fg: '#C8472F', bg: '#F8E3DD', bd: '#efc8bd' },
};

export const KANBAN_STAGES = [
  'identified',
  'proposed',
  'validated',
  'committed',
  'in_flight',
  'realized',
] as const;

export const PENDING_STAGES = new Set(['identified', 'proposed', 'validated']);
export const COMMITTED_STAGES = new Set(['committed', 'in_flight', 'realized']);
