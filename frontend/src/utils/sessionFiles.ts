export interface ManifestFileEntry {
  name?: string;
  content_type?: string;
  size_bytes?: number;
  schema?: unknown;
}

const SPEND_EXTENSIONS = new Set(['.csv', '.xlsx', '.xls']);

export function fileExtension(name: string): string {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

export function isSpendReadyFile(name: string): boolean {
  return SPEND_EXTENSIONS.has(fileExtension(name));
}

export function fileUploadStatus(name: string): 'spend' | 'document' | 'unsupported' {
  const ext = fileExtension(name);
  if (SPEND_EXTENSIONS.has(ext)) return 'spend';
  if (['.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.webp'].includes(ext)) return 'document';
  return 'unsupported';
}

export function formatFileSize(bytes?: number): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
