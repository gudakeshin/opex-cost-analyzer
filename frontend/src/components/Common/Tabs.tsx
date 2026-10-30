import React from 'react';
import { TabList } from './TabList';

export interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  /** Accessible name for the tab group. */
  label?: string;
}

export const Tabs: React.FC<TabsProps> = ({ tabs, activeId, onChange, label = 'Sections' }) => (
  <TabList
    tabs={tabs}
    activeId={activeId}
    onChange={onChange}
    label={label}
    className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto"
    tabClassName={(active) =>
      `px-6 py-4 font-medium whitespace-nowrap transition-colors ${
        active
          ? 'text-brand-primary border-b-2 border-brand-primary'
          : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
      }`
    }
  />
);
