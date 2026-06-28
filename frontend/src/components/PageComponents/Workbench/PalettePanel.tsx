import React from 'react';
import type { WorkbenchCatalog, WorkbenchSkill } from '../../../types';

interface PalettePanelProps {
  catalog: WorkbenchCatalog;
  selected: string[];
  onToggle: (name: string) => void;
}

function prettyName(name: string): string {
  return name
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

export const PalettePanel: React.FC<PalettePanelProps> = ({ catalog, selected, onToggle }) => {
  const selectedSet = new Set(selected);
  const byTier = catalog.tiers
    .map((tier) => ({
      tier,
      skills: catalog.skills.filter((s) => s.tier === tier),
    }))
    .filter((g) => g.skills.length > 0);

  return (
    <div className="space-y-5">
      {byTier.map(({ tier, skills }) => (
        <div key={tier}>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-brand-muted mb-2">
            {tier}
          </h3>
          <div className="space-y-1.5">
            {skills.map((skill: WorkbenchSkill) => {
              const active = selectedSet.has(skill.name);
              const hardReq = skill.data_requirements.length > 0;
              return (
                <button
                  key={skill.name}
                  type="button"
                  onClick={() => onToggle(skill.name)}
                  title={skill.description}
                  className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                    active
                      ? 'border-deloitte-green bg-green-50 text-brand-ink'
                      : 'border-brand-border hover:bg-brand-surface-muted text-brand-ink'
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{prettyName(skill.name)}</span>
                    <span className="text-xs shrink-0">{active ? '✓' : '+'}</span>
                  </span>
                  {(hardReq || skill.degrades_without.length > 0) && (
                    <span className="block mt-0.5 text-[10px] text-amber-700">
                      {hardReq
                        ? `needs ${skill.data_requirements.join(', ')}`
                        : `better with ${skill.degrades_without.join(', ')}`}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};
