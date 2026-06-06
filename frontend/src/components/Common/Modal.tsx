import React, { useEffect } from 'react';
import { Button } from './Button';

interface ModalProps {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  onConfirm?: () => void;
  confirmLabel?: string;
  confirmVariant?: 'primary' | 'danger';
  size?: 'md' | 'lg' | 'xl';
}

const MODAL_SIZE_CLASS: Record<NonNullable<ModalProps['size']>, string> = {
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
};

export const Modal: React.FC<ModalProps> = ({
  open,
  title,
  children,
  onClose,
  onConfirm,
  confirmLabel = 'Confirm',
  confirmVariant = 'primary',
  size = 'md',
}) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="modal-overlay" onClick={onClose} role="presentation">
        <div
          className={`modal-content p-6 ${MODAL_SIZE_CLASS[size]}`}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
        >
          <h2 id="modal-title" className="text-lg font-semibold text-gray-900 mb-4">
            {title}
          </h2>
          {children}
          <div className="flex justify-end gap-2 mt-6">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            {onConfirm && (
              <Button variant={confirmVariant === 'danger' ? 'danger' : 'primary'} onClick={onConfirm}>
                {confirmLabel}
              </Button>
            )}
          </div>
        </div>
      </div>
    </>
  );
};
