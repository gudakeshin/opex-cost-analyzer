import axios, { AxiosError } from 'axios';

const client = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
});

export function getApiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string | { message?: string; error?: string } }>;
    const detail = ax.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') {
      if ('message' in detail && detail.message) return String(detail.message);
      if ('error' in detail && detail.error) return String(detail.error);
    }
    return ax.message;
  }
  if (err instanceof Error) return err.message;
  return 'Request failed';
}

export async function apiGet<T>(url: string): Promise<T> {
  const { data } = await client.get<T>(url);
  return data;
}

export async function apiPost<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await client.post<T>(url, body);
  return data;
}

export async function apiPut<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await client.put<T>(url, body);
  return data;
}

export async function apiPatch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await client.patch<T>(url, body);
  return data;
}

export async function apiDelete<T>(url: string): Promise<T> {
  const { data } = await client.delete<T>(url);
  return data;
}

export async function apiUpload<T>(
  url: string,
  formData: FormData,
): Promise<T> {
  const { data } = await client.post<T>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export { client as apiClient };

export type ChatStreamEvent =
  | { event: 'run_id'; data: { run_id: string } }
  | { event: 'progress'; data: { phase: string; message: string } }
  | { event: 'thinking'; data: { chunk: string } }
  | { event: 'token'; data: { delta: string } }
  | { event: 'done'; data: Record<string, unknown> }
  | { event: 'error'; data: { error?: string; message?: string } };

function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = 'message';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim();
    if (line.startsWith('data: ')) data += line.slice(6);
  }
  if (!data) return null;
  return { event, data };
}

/** POST + SSE stream for `/api/v1/chat/stream`. */
export async function streamChatPost(
  url: string,
  body: unknown,
  onEvent: (ev: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<Record<string, unknown> | null> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Stream request failed (${res.status})`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body for SSE stream');

  const decoder = new TextDecoder();
  let buffer = '';
  let finalPayload: Record<string, unknown> | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const parsed = parseSseBlock(part.trim());
      if (!parsed) continue;
      const payload = JSON.parse(parsed.data) as Record<string, unknown>;
      const event = parsed.event as ChatStreamEvent['event'];
      onEvent({ event, data: payload } as ChatStreamEvent);
      if (event === 'done') finalPayload = payload;
      if (event === 'error') {
        throw new Error(String(payload.message || payload.error || 'Stream error'));
      }
    }
  }
  return finalPayload;
}
