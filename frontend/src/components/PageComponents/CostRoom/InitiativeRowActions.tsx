import React from 'react';
import { Button } from '../../Common/Button';
import { canAcceptInitiative, stageLabel } from '../../../utils/initiativeHelpers';
import type { Initiative } from '../../../types';

interface InitiativeRowActionsProps {
  initiative: Initiative;
  onView: () => void;
  onAccept: (id: string) => void;
  onDefer: (id: string) => void;
  onReject: (id: string) => void;
}

export const InitiativeRowActions: React.FC<InitiativeRowActionsProps> = ({
  initiative,
  onView,
  onAccept,
  onDefer,
  onReject,
}) => {
  const id = initiative.initiative_id;
  const stage = initiative.stage;
  const accepted = stage === 'committed' || stage === 'in_flight' || stage === 'realized';
  const canAct = stage === 'identified' || stage === 'proposed';
  const acceptAllowed = canAcceptInitiative(initiative);

  if (accepted) {
    return <span className="text-sm font-medium text-success">Accepted ✓</span>;
  }
  if (stage === 'deferred') {
    return <span className="text-sm text-brand-muted">{stageLabel(stage)}</span>;
  }
  if (stage === 'rejected') {
    return <span className="text-sm text-error">{stageLabel(stage)}</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={onView}>
        View
      </Button>
      {canAct && (
        <>
          <Button
            variant="primary"
            className="!px-2 !py-1 text-xs"
            disabled={!acceptAllowed}
            title={
              acceptAllowed
                ? 'Accept initiative'
                : 'AQS below Gate-2 threshold (0.65). CFO override not available in this build.'
            }
            onClick={() => onAccept(id)}
          >
            Accept
          </Button>
          <Button variant="secondary" className="!px-2 !py-1 text-xs" onClick={() => onDefer(id)}>
            Defer
          </Button>
          <Button variant="danger" className="!px-2 !py-1 text-xs" onClick={() => onReject(id)}>
            Reject
          </Button>
        </>
      )}
    </div>
  );
};
