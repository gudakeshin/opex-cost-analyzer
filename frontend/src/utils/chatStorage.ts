import type { ChatMessage } from '../types';

const PREFIX = 'opex_chat_';

/** Omit spend totals from persisted chat — live session analysis is the source of truth. */
export function stripSpendFieldsForStorage(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((m) => {
    if (!m.insight_snapshot) return m;
    const snap = m.insight_snapshot;
    return {
      ...m,
      insight_snapshot: {
        ...snap,
        total_spend: 0,
        top_categories: [],
        chart_data: undefined,
        line_count: undefined,
        ingestion_note: undefined,
        spend_base_revision: undefined,
      },
    };
  });
}

export function loadChatMessages(sessionId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(`${PREFIX}${sessionId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatMessage[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveChatMessages(sessionId: string, messages: ChatMessage[]): void {
  try {
    localStorage.setItem(
      `${PREFIX}${sessionId}`,
      JSON.stringify(stripSpendFieldsForStorage(messages)),
    );
  } catch {
    /* quota exceeded — ignore */
  }
}

export function clearChatMessages(sessionId: string): void {
  localStorage.removeItem(`${PREFIX}${sessionId}`);
}
