import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownProps {
  children: string;
  className?: string;
}

/**
 * Renders assistant chat text as GitHub-flavored markdown (bullets, numbered lists,
 * headings, tables, links) with compact Tailwind styling that matches the chat theme.
 */
export const Markdown: React.FC<MarkdownProps> = ({ children, className }) => (
  <div className={className}>
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
        ul: ({ children }) => <ul className="list-disc pl-5 mb-2 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-5 mb-2 space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        h1: ({ children }) => <h3 className="text-sm font-bold mt-3 mb-1">{children}</h3>,
        h2: ({ children }) => <h3 className="text-sm font-bold mt-3 mb-1">{children}</h3>,
        h3: ({ children }) => (
          <h4 className="text-xs font-bold uppercase tracking-wide text-brand-muted mt-3 mb-1">{children}</h4>
        ),
        h4: ({ children }) => (
          <h4 className="text-xs font-bold uppercase tracking-wide text-brand-muted mt-2 mb-1">{children}</h4>
        ),
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        a: ({ href, children }) => {
          const isExternal = /^https?:\/\//i.test(href ?? '');
          return (
            <a
              href={href}
              className="text-deloitte-green underline underline-offset-2 font-medium"
              {...(isExternal ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            >
              {children}
            </a>
          );
        },
        code: ({ children }) => (
          <code className="px-1 py-0.5 rounded bg-brand-surface-muted text-[0.85em] font-mono">{children}</code>
        ),
        pre: ({ children }) => (
          <pre className="my-2 p-2 rounded-lg bg-brand-surface-muted overflow-x-auto text-[11px] font-mono">{children}</pre>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="w-full text-left border-collapse text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="border-b border-brand-border">{children}</thead>,
        th: ({ children }) => <th className="px-2 py-1 font-semibold text-brand-muted">{children}</th>,
        td: ({ children }) => (
          <td className="px-2 py-1 border-b border-brand-border/50 tabular-nums">{children}</td>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-brand-border pl-3 italic text-brand-muted my-2">{children}</blockquote>
        ),
        hr: () => <hr className="my-3 border-brand-border" />,
      }}
    >
      {children}
    </ReactMarkdown>
  </div>
);
