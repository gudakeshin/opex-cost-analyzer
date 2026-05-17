/** Normalize pathname for sidebar active state (handles /ui basename in dev). */
export function navPathname(pathname: string): string {
  let p = pathname || '/';
  if (p.startsWith('/ui')) {
    p = p.slice(3) || '/';
  }
  if (!p.startsWith('/')) {
    p = `/${p}`;
  }
  if (p.length > 1 && p.endsWith('/')) {
    p = p.slice(0, -1);
  }
  return p || '/';
}

export function isNavActive(currentPath: string, to: string): boolean {
  const current = navPathname(currentPath);
  const target = navPathname(to);
  if (target === '/') {
    return current === '/';
  }
  return current === target || current.startsWith(`${target}/`);
}
