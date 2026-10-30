import React, { useCallback, useRef, useState } from 'react';
import { Modal } from '../components/Common/Modal';

export interface ConfirmOptions {
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  /** Use for irreversible actions (delete, publish). */
  danger?: boolean;
}

/**
 * Promise-based confirmation built on the shared Modal.
 *
 *   const [confirm, confirmDialog] = useConfirm();
 *   if (!(await confirm({ title: 'Delete run?', message: '…', danger: true }))) return;
 *   …render {confirmDialog} once in the component's JSX.
 */
export function useConfirm(): [(opts: ConfirmOptions) => Promise<boolean>, React.ReactNode] {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);
  const resolver = useRef<((ok: boolean) => void) | null>(null);

  const settle = useCallback((ok: boolean) => {
    resolver.current?.(ok);
    resolver.current = null;
    setOpts(null);
  }, []);

  const confirm = useCallback(
    (next: ConfirmOptions) =>
      new Promise<boolean>((resolve) => {
        // A second request while one is open cancels the first.
        resolver.current?.(false);
        resolver.current = resolve;
        setOpts(next);
      }),
    [],
  );

  const dialog = (
    <Modal
      open={opts !== null}
      title={opts?.title ?? ''}
      onClose={() => settle(false)}
      onConfirm={() => settle(true)}
      confirmLabel={opts?.confirmLabel ?? 'Confirm'}
      confirmVariant={opts?.danger ? 'danger' : 'primary'}
    >
      <div className="text-sm text-gray-700">{opts?.message}</div>
    </Modal>
  );

  return [confirm, dialog];
}
