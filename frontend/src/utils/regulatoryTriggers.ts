/** Client-side count of regulatory trigger table rows (mirrors backend parser). */
export function parse_regulatory_triggers_count(md: string): number {
  if (!md) return 0;
  let inTable = false;
  let count = 0;
  for (const line of md.split('\n')) {
    const stripped = line.trim();
    if (stripped.startsWith('| Trigger')) {
      inTable = true;
      continue;
    }
    if (!inTable) continue;
    if (stripped.startsWith('|---')) continue;
    if (!stripped.startsWith('|')) break;
    if (stripped.split('|').length >= 4) count += 1;
  }
  return count;
}
