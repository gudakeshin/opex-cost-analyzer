import { useEffect, useRef } from 'react';
import { useUnsavedChanges } from '../context/UnsavedChangesContext';

interface UseAutosaveOptions<T> {
  /** Stable id identifying this autosave registrant (e.g. page name). */
  id: string;
  /** Snapshot of the data to persist. A new reference/value triggers a debounced save. */
  data: T;
  /** Persist `data`. Should throw/reject on failure. */
  onSave: (data: T) => Promise<void>;
  /** Skip saving while true (e.g. during initial hydration). */
  enabled: boolean;
  debounceMs?: number;
}

/**
 * Debounced autosave: watches `data`, PATCHes via `onSave` after `debounceMs` of
 * inactivity, and reports dirty/saving/saved status to UnsavedChangesContext so a
 * global indicator and navigation guard can react to it.
 */
export function useAutosave<T>({ id, data, onSave, enabled, debounceMs = 500 }: UseAutosaveOptions<T>): void {
  const { setStatus, clear } = useUnsavedChanges();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dataRef = useRef(data);
  const onSaveRef = useRef(onSave);
  const wasEnabledRef = useRef(false);
  const dirtyRef = useRef(false);
  dataRef.current = data;
  onSaveRef.current = onSave;

  useEffect(() => {
    if (!enabled) {
      wasEnabledRef.current = false;
      return;
    }
    const justEnabled = !wasEnabledRef.current;
    wasEnabledRef.current = true;
    // Skip the change triggered by hydration finishing (not a user edit).
    if (justEnabled) return;

    dirtyRef.current = true;
    setStatus(id, 'dirty');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setStatus(id, 'saving');
      onSaveRef
        .current(dataRef.current)
        .then(() => {
          dirtyRef.current = false;
          setStatus(id, 'saved');
        })
        .catch(() => setStatus(id, 'error'));
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, enabled]);

  useEffect(() => {
    return () => {
      clear(id);
      if (timerRef.current) clearTimeout(timerRef.current);
      if (dirtyRef.current) {
        // Component is gone so there is no UI to surface this in; at least
        // leave a trace instead of losing the failure silently.
        onSaveRef.current(dataRef.current).catch((err) => {
          console.error(`autosave(${id}): final save on unmount failed`, err);
        });
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
}
