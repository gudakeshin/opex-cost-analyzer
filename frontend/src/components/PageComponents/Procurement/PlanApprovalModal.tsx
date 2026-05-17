import React from 'react';
import { Modal } from '../../Common/Modal';
import type { ChatPlanPreview } from '../../../types';

interface PlanApprovalModalProps {
  open: boolean;
  plan: ChatPlanPreview | null;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const PlanApprovalModal: React.FC<PlanApprovalModalProps> = ({
  open,
  plan,
  loading,
  onConfirm,
  onCancel,
}) => (
  <Modal
    open={open}
    title="Review analysis plan"
    onClose={onCancel}
    onConfirm={onConfirm}
    confirmLabel={loading ? 'Running…' : 'Confirm & run'}
  >
    <p className="text-sm text-brand-muted mb-4">
      Human-in-the-loop: confirm the planned skills before the Act phase executes.
    </p>
    {plan?.user_summary ? (
      <p className="text-sm text-brand-ink whitespace-pre-wrap border-l-4 border-brand-green pl-3">
        {plan.user_summary}
      </p>
    ) : (
      <p className="text-sm text-brand-muted">No plan summary returned.</p>
    )}
    {plan?.planned_skills && plan.planned_skills.length > 0 && (
      <ul className="mt-4 text-sm list-disc list-inside text-brand-ink">
        {plan.planned_skills.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    )}
  </Modal>
);
