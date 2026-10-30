import { useEffect } from 'react';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';

/**
 * Registers a manual-save page's dirty flag with the global unsaved-changes
 * indicator/navigation guard, without taking over saving (unlike useAutosave).
 */
export function useUnsavedGuard(id: string, isDirty: boolean): void {
  const { setStatus, clear } = useUnsavedChanges();

  useEffect(() => {
    setStatus(id, isDirty ? 'dirty' : 'saved');
  }, [id, isDirty, setStatus]);

  useEffect(() => {
    return () => clear(id);
  }, [id, clear]);
}
