import React, { useRef } from 'react';

export interface TabListItem {
  id: string;
  label: React.ReactNode;
}

interface TabListProps {
  tabs: TabListItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Accessible name for the tab group. */
  label: string;
  className?: string;
  /** Classes for one tab button, given whether it is the active one. */
  tabClassName: (active: boolean) => string;
}

/**
 * Accessible tab strip: tablist/tab roles, aria-selected, roving tabindex and
 * Left/Right/Home/End keys. Selection follows focus (automatic activation).
 */
export const TabList: React.FC<TabListProps> = ({ tabs, activeId, onChange, label, className, tabClassName }) => {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next = -1;
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length;
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    const target = tabs[next];
    onChange(target.id);
    refs.current[target.id]?.focus();
  };

  return (
    <div role="tablist" aria-label={label} className={className}>
      {tabs.map((tab, i) => {
        const active = tab.id === activeId;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            id={`tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={tabClassName(active)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
};
