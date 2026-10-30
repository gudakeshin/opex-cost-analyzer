import React, { useEffect, useId } from 'react';
import { useFocusTrap } from '../../hooks/useFocusTrap';

interface DrawerProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

export const Drawer: React.FC<DrawerProps> = ({ open, title, onClose, children }) => {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLElement>(open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      {/* Pointer-only backdrop; keyboard users close with Escape or the Close button. */}
      <button
        type="button"
        tabIndex={-1}
        className="fixed inset-0 bg-black/40 z-40"
        aria-label="Close drawer"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="fixed right-0 top-0 h-full w-full max-w-md bg-white dark:bg-gray-900 shadow-xl z-50 flex flex-col outline-none"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 id={titleId} className="text-lg font-semibold text-gray-900 dark:text-white">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </aside>
    </>
  );
};
