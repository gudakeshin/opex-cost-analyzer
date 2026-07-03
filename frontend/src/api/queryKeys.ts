export const sessionKeys = {
  manifest: (sessionId: string | null | undefined) => ['session', sessionId, 'manifest'] as const,
  status: (sessionId: string | null | undefined) => ['session', sessionId, 'status'] as const,
  analysis: (sessionId: string | null | undefined) => ['session', sessionId, 'analysis'] as const,
  list: () => ['sessions'] as const,
};

export const engagementKeys = {
  list: () => ['engagements'] as const,
  detail: (engagementId: string | null | undefined) => ['engagements', engagementId] as const,
};

export const costRoomKeys = {
  initiatives: (engagementId: string | null | undefined) => ['initiatives', engagementId] as const,
  summary: (engagementId: string | null | undefined) => ['pipelineSummary', engagementId] as const,
  sensitivity: (sessionId: string | null | undefined, scenario: string) =>
    ['sensitivity', sessionId, scenario] as const,
  conflicts: (sessionId: string | null | undefined) => ['conflicts', sessionId] as const,
  fpaTab: (tab: string, sessionId: string | null | undefined) => ['fpaTab', tab, sessionId] as const,
  milestones: (initiativeId: string | null | undefined) => ['milestones', initiativeId] as const,
  provenance: (initiativeId: string | null | undefined) => ['provenance', initiativeId] as const,
  auditLogLatest: (trigger: number) => ['auditLog', 'latest', trigger] as const,
};
