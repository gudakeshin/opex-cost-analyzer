import React from 'react';

export interface TabItem {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
}

export const Tabs: React.FC<TabsProps> = ({ tabs, activeId, onChange }) => (
  <div className="flex border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
    {tabs.map((tab) => (
      <button
        key={tab.id}
        type="button"
        onClick={() => onChange(tab.id)}
        className={`px-6 py-4 font-medium whitespace-nowrap transition-colors ${
          activeId === tab.id
            ? 'text-deloitte-green border-b-2 border-deloitte-green'
            : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-300'
        }`}
      >
        {tab.label}
      </button>
    ))}
  </div>
);
