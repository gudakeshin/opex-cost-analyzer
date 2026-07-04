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
  auditLog: (limit: number) => ['auditLog', limit] as const,
};

export const procurementKeys = {
  engagementDocuments: (engagementId: string | null | undefined) =>
    ['engagementDocuments', engagementId] as const,
  llmModels: () => ['llmModels'] as const,
  chatProgress: (runId: string | null | undefined) => ['chatProgress', runId] as const,
};

export const diagnosticKeys = {
  deepResearchStatus: (interactionId: string | null | undefined, sessionId: string | null | undefined) =>
    ['deepResearchStatus', interactionId, sessionId] as const,
};

export const skillsKeys = {
  catalog: () => ['skillsCatalog'] as const,
  dependencies: () => ['skillsDependencies'] as const,
};

export const workbenchKeys = {
  catalog: () => ['workbenchCatalog'] as const,
  runs: (engagementId: string | null | undefined, sessionId: string | null | undefined) =>
    ['workbenchRuns', engagementId, sessionId] as const,
  progress: (runId: string | null | undefined) => ['workbenchProgress', runId] as const,
};

export const benchmarkKeys = {
  sectorPacks: () => ['sectorPacks'] as const,
  peerSets: () => ['benchmarkPeerSets'] as const,
  datasets: () => ['benchmarkDatasets'] as const,
  coverage: (datasetId: string | null | undefined) => ['benchmarkCoverage', datasetId] as const,
  packDetail: (packId: string | null | undefined) => ['sectorPackDetail', packId] as const,
};
