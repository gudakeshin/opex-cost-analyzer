import React from 'react';
import { Link } from 'react-router-dom';

interface RecommendedBadgeProps {
  /** The detected/recommended display value. */
  label: string;
  /** True when the current selection already equals the recommendation. */
  matches: boolean;
  /** Apply handler — surfaced as a "Use" link only when the selection differs. */
  onApply?: () => void;
  /** Route to edit the recommendation (e.g. Diagnostic page from Analysis). */
  changeLink?: string;
  className?: string;
}

/**
 * Compact "Recommended from your documents" chip used beside the company and
 * industry inputs on the Diagnostic and Analysis pages. The recommendation is
 * auto-detected and pre-filled; this only surfaces the basis and an override-back
 * affordance when the user has changed it.
 */
export const RecommendedBadge: React.FC<RecommendedBadgeProps> = ({
  label,
  matches,
  onApply,
  changeLink,
  className = '',
}) => {
  if (!label) return null;
  return (
    <span className={`inline-flex flex-wrap items-center gap-1 text-[11px] text-brand-muted ${className}`}>
      <span className="inline-flex items-center gap-1 rounded bg-brand-surface-muted px-1.5 py-0.5">
        <span aria-hidden>✨</span>
        Recommended from your documents:{' '}
        <span className="font-medium text-brand-ink">{label}</span>
      </span>
      {!matches && onApply && (
        <button
          type="button"
          onClick={onApply}
          className="text-deloitte-green underline underline-offset-2 hover:opacity-80"
        >
          Use recommended
        </button>
      )}
      {changeLink && (
        <Link
          to={changeLink}
          className="text-deloitte-green underline underline-offset-2 hover:opacity-80"
        >
          {matches ? 'Change' : 'Change in Diagnostic'}
        </Link>
      )}
    </span>
  );
};
