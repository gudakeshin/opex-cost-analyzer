import { useEffect } from 'react';
import { useFocusTrap } from './useFocusTrap';

/**
 * Dialog behaviour for hand-built overlays: traps focus while open, restores it on close,
 * and closes on Escape. Attach the returned ref to the dialog panel and give that element
 * role="dialog", aria-modal="true", an accessible name and tabIndex={-1}.
 */
export function useDialogA11y<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useFocusTrap<T>(open);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  return ref;
}
