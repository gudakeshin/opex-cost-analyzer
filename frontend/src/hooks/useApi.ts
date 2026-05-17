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
