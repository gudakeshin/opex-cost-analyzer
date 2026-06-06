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
    <p className="text-sm text-gray-600 mb-4">
      Human-in-the-loop: confirm the planned skills before the Act phase executes.
    </p>
    {plan?.user_summary ? (
      <p className="text-sm text-gray-900 whitespace-pre-wrap border-l-4 border-brand-green bg-gray-50 rounded-r-lg pl-4 py-2">
        {plan.user_summary}
      </p>
    ) : (
      <p className="text-sm text-gray-500">No plan summary returned.</p>
    )}
    {plan?.planned_skills && plan.planned_skills.length > 0 && (
      <ul className="mt-4 text-sm list-disc list-inside text-gray-900">
        {plan.planned_skills.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    )}
  </Modal>
);
