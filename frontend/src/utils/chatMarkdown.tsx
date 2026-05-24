import React from 'react';

/** Minimal inline markdown: **bold** and [label](url). */
export function renderChatMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(<span key={key++}>{text.slice(last, match.index)}</span>);
    }
    const token = match[0];
    if (token.startsWith('**')) {
      parts.push(
        <strong key={key++} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      const linkMatch = /\[([^\]]+)\]\(([^)]+)\)/.exec(token);
      if (linkMatch) {
        const href = linkMatch[2];
        const isExternal = /^https?:\/\//i.test(href);
        parts.push(
          <a
            key={key++}
            href={href}
            className="text-deloitte-green underline underline-offset-2 font-medium"
            {...(isExternal ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
          >
            {linkMatch[1]}
          </a>,
        );
      }
    }
    last = match.index + token.length;
  }

  if (last < text.length) {
    parts.push(<span key={key++}>{text.slice(last)}</span>);
  }

  return parts.length > 0 ? parts : [<span key={0}>{text}</span>];
}

export function artefactLinks(
  artefacts: Record<string, unknown> | string[] | undefined,
): string[] {
  if (!artefacts) return [];
  if (Array.isArray(artefacts)) {
    return artefacts.filter((u): u is string => typeof u === 'string' && u.length > 0);
  }
  const urls: string[] = [];
  for (const v of Object.values(artefacts)) {
    if (typeof v === 'string' && (v.startsWith('/') || /^https?:\/\//i.test(v))) {
      urls.push(v);
    } else if (Array.isArray(v)) {
      for (const item of v) {
        if (typeof item === 'string' && item.length > 0) urls.push(item);
      }
    }
  }
  return urls;
}
