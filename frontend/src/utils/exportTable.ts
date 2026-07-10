/** CSV/TSV helpers for positional query/sensitivity result tables. */

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = typeof value === 'number' && Number.isFinite(value) ? String(value) : String(value);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function escapeTsvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = typeof value === 'number' && Number.isFinite(value) ? String(value) : String(value);
  return s.replace(/\t/g, ' ').replace(/\n/g, ' ').replace(/\r/g, '');
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  const header = columns.map(escapeCsvCell).join(',');
  const body = rows.map((row) => columns.map((_, i) => escapeCsvCell(row[i])).join(','));
  return [header, ...body].join('\n');
}

export function toTsv(columns: string[], rows: unknown[][]): string {
  const header = columns.map(escapeTsvCell).join('\t');
  const body = rows.map((row) => columns.map((_, i) => escapeTsvCell(row[i])).join('\t'));
  return [header, ...body].join('\n');
}

export function downloadTextFile(filename: string, content: string, mime = 'text/csv;charset=utf-8'): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
}
