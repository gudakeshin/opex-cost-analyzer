import { apiGet } from '../hooks/useApi';
import type { SessionSummary } from '../types';

/**
 * The engagement's most recent session that already holds a completed analysis,
 * or null when none exists.
 *
 * An engagement can accumulate several sessions (each "Run analysis" / session
 * recreation adds one). Only some carry analysis. If the active `sessionId`
 * points at an empty sibling, the Analysis workspace and Cost Room render blank
 * even though a finished analysis exists for the engagement. Callers use this to
 * adopt the analyzed session instead of landing on (or creating) an empty one.
 */
export async function latestAnalyzedSessionId(
  engagementId: string,
): Promise<string | null> {
  try {
    const sessions = await apiGet<SessionSummary[]>('/api/v1/sessions');
    const analyzed = sessions
      .filter((s) => s.engagement_id === engagementId && s.has_analysis)
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    return analyzed[0]?.session_id ?? null;
  } catch {
    return null;
  }
}
