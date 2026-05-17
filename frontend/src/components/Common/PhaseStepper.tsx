import React from 'react';

const PHASES = ['Observe', 'Plan', 'Act', 'Reflect'] as const;
export type OparPhase = (typeof PHASES)[number];

interface PhaseStepperProps {
  activePhase?: OparPhase | string;
}

export const PhaseStepper: React.FC<PhaseStepperProps> = ({ activePhase = 'Observe' }) => {
  const activeIdx = PHASES.findIndex(
    (p) => p.toLowerCase() === String(activePhase).toLowerCase(),
  );
  const idx = activeIdx >= 0 ? activeIdx : 0;

  return (
    <nav aria-label="OPAR workflow" className="flex items-center gap-1 flex-wrap">
      {PHASES.map((phase, i) => {
        const done = i < idx;
        const active = i === idx;
        return (
          <React.Fragment key={phase}>
            {i > 0 && (
              <span className="text-brand-border mx-1" aria-hidden>
                →
              </span>
            )}
            <span
              className={`text-xs font-semibold uppercase tracking-wide px-2 py-1 rounded ${
                active
                  ? 'bg-brand-green text-white'
                  : done
                    ? 'bg-brand-navy/10 text-brand-navy'
                    : 'bg-brand-surface-muted text-brand-muted'
              }`}
            >
              {phase}
            </span>
          </React.Fragment>
        );
      })}
    </nav>
  );
};
