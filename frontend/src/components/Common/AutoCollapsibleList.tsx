import React from 'react';
import { CollapsibleOverflow } from './CollapsibleOverflow';

interface AutoCollapsibleListProps<T> {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
  getKey: (item: T, index: number) => string;
  maxLines?: number;
  className?: string;
  listClassName?: string;
  expandLabel?: string;
  collapseLabel?: string;
}

/** Renders a list and auto-collapses when content exceeds `maxLines` of height. */
export function AutoCollapsibleList<T>({
  items,
  renderItem,
  getKey,
  maxLines = 2,
  className = '',
  listClassName = 'space-y-2',
  expandLabel,
  collapseLabel,
}: AutoCollapsibleListProps<T>) {
  if (!items.length) return null;

  return (
    <CollapsibleOverflow
      maxLines={maxLines}
      className={className}
      expandLabel={expandLabel}
      collapseLabel={collapseLabel}
    >
      <ul className={listClassName}>
        {items.map((item, index) => (
          <li key={getKey(item, index)}>{renderItem(item, index)}</li>
        ))}
      </ul>
    </CollapsibleOverflow>
  );
};
