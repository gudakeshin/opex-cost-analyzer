import React, { useEffect, useState } from 'react';
import { Modal } from '../../Common/Modal';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { BusinessClarification } from '../../../types';

export type ClarificationModalVariant = 'observe' | 'sme_probe';

export interface SmeProbeModalMeta {
  category_name: string;
  affected_categories?: string[];
  scope?: 'portfolio' | 'category';
  saving_at_stake?: number;
  index: number;
  total: number;
  currency?: string;
}

interface BusinessClarificationModalProps {
  open: boolean;
  clarification: BusinessClarification | null;
  loading?: boolean;
  variant?: ClarificationModalVariant;
  probeMeta?: SmeProbeModalMeta | null;
  onConfirm: (selectedOption: string | null, freeText: string) => void;
  onCancel: () => void;
}

const DEFERRAL_PATTERNS = [
  /upload/i,
  /attach/i,
  /session settings/i,
  /enter.*revenue/i,
  /select industry/i,
  /defer/i,
  /wait until/i,
];

function optionImpliesDeferral(option: string): boolean {
  return DEFERRAL_PATTERNS.some((p) => p.test(option));
}

export const BusinessClarificationModal: React.FC<BusinessClarificationModalProps> = ({
  open,
  clarification,
  loading,
  variant = 'observe',
  probeMeta,
  onConfirm,
  onCancel,
}) => {
  const isSmeProbe = variant === 'sme_probe';
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [freeText, setFreeText] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setSelectedOption(null);
      setFreeText('');
      setValidationError(null);
    }
  }, [open, clarification?.question]);

  const handleConfirm = () => {
    const trimmedFree = freeText.trim();
    if (!selectedOption && !trimmedFree) {
      setValidationError('Select an option or enter custom business logic to continue.');
      return;
    }
    if (selectedOption && optionImpliesDeferral(selectedOption) && !trimmedFree) {
      setValidationError(
        'This option requires providing data first. Upload files or update session settings, then resend your question.',
      );
      return;
    }
    setValidationError(null);
    onConfirm(selectedOption, trimmedFree);
  };

  const modalTitle = isSmeProbe
    ? probeMeta
      ? `Assumption probe (${probeMeta.index + 1} of ${probeMeta.total})`
      : 'Assumption probe'
    : 'Business clarification required';

  const confirmLabel = loading
    ? isSmeProbe
      ? 'Submitting…'
      : 'Continuing…'
    : isSmeProbe
      ? probeMeta && probeMeta.index + 1 < probeMeta.total
        ? 'Submit & next probe'
        : 'Submit answer'
      : 'Continue analysis';

  return (
    <Modal
      open={open}
      title={modalTitle}
      onClose={onCancel}
      onConfirm={handleConfirm}
      confirmLabel={confirmLabel}
      size="xl"
    >
      <p className="text-sm text-gray-600 leading-relaxed mb-4">
        {isSmeProbe
          ? 'Human-in-the-loop: strengthen the value case by answering this SME assumption probe before we treat savings as evidenced.'
          : 'Human-in-the-loop: the agent paused because it needs your business judgment before proceeding.'}
      </p>
      {isSmeProbe && probeMeta && (
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
          {probeMeta.scope === 'portfolio' || (probeMeta.affected_categories?.length ?? 0) > 1
            ? `Applies to: ${(probeMeta.affected_categories?.length ? probeMeta.affected_categories : [probeMeta.category_name]).join(', ')}`
            : probeMeta.category_name}
          {probeMeta.saving_at_stake && probeMeta.saving_at_stake > 0 && probeMeta.currency
            ? ` · ${formatSpendAmount(probeMeta.saving_at_stake, probeMeta.currency)} at stake`
            : ''}
        </p>
      )}
      {clarification?.question ? (
        <p className="text-base font-semibold text-gray-900 whitespace-pre-wrap border-l-4 border-brand-green bg-gray-50 rounded-r-lg pl-4 pr-3 py-3 mb-3 leading-relaxed">
          {clarification.question}
        </p>
      ) : (
        <p className="text-sm text-gray-500 mb-3">No clarification question returned.</p>
      )}
      {clarification?.reasoning && (
        <p className="text-sm text-gray-600 leading-relaxed mb-4">{clarification.reasoning}</p>
      )}
      {clarification?.options && clarification.options.length > 0 && (
        <div className="flex flex-col gap-2 mb-4">
          {clarification.options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => {
                setSelectedOption(opt);
                setValidationError(null);
              }}
              className={`text-left text-sm px-4 py-3 rounded-lg border transition-colors ${
                selectedOption === opt
                  ? 'border-brand-green bg-emerald-50 text-gray-900 font-medium'
                  : 'border-gray-300 bg-white hover:bg-gray-50 text-gray-900'
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      <label className="block text-sm font-medium text-gray-900 mb-2" htmlFor="clarification-free-text">
        {isSmeProbe ? 'Your answer (required if no option selected)' : 'Custom business logic (optional)'}
      </label>
      <textarea
        id="clarification-free-text"
        value={freeText}
        onChange={(e) => {
          setFreeText(e.target.value);
          setValidationError(null);
        }}
        placeholder='e.g. "Ignore the variance if it is strictly related to the Wonder Cement subsidiary"'
        rows={3}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg bg-white text-gray-900 placeholder:text-gray-400 text-sm font-sans resize-y"
      />
      {validationError && (
        <p className="text-xs text-red-600 mt-2" role="alert">
          {validationError}
        </p>
      )}
    </Modal>
  );
};
