import type { ChatMessage } from '../types';

const PREFIX = 'opex_chat_';

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
    localStorage.setItem(`${PREFIX}${sessionId}`, JSON.stringify(messages));
  } catch {
    /* quota exceeded — ignore */
  }
}

export function clearChatMessages(sessionId: string): void {
  localStorage.removeItem(`${PREFIX}${sessionId}`);
}
