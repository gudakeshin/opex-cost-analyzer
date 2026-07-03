import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

export type SaveStatus = 'idle' | 'dirty' | 'saving' | 'saved' | 'error';

interface Registrant {
  status: SaveStatus;
}

interface UnsavedChangesContextValue {
  setStatus: (id: string, status: SaveStatus) => void;
  clear: (id: string) => void;
  hasUnsaved: boolean;
  isSaving: boolean;
  hasError: boolean;
  confirmNavigation: () => boolean;
}

const UnsavedChangesContext = createContext<UnsavedChangesContextValue | null>(null);

export const UnsavedChangesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [registry, setRegistry] = useState<Record<string, Registrant>>({});
  const registryRef = useRef(registry);
  registryRef.current = registry;

  const setStatus = useCallback((id: string, status: SaveStatus) => {
    setRegistry((prev) => {
      if (prev[id]?.status === status) return prev;
      return { ...prev, [id]: { status } };
    });
  }, []);

  const clear = useCallback((id: string) => {
    setRegistry((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  const hasUnsaved = useMemo(
    () => Object.values(registry).some((r) => r.status === 'dirty' || r.status === 'saving'),
    [registry],
  );
  const isSaving = useMemo(() => Object.values(registry).some((r) => r.status === 'saving'), [registry]);
  const hasError = useMemo(() => Object.values(registry).some((r) => r.status === 'error'), [registry]);

  // 'error' counts as unsaved for navigation purposes: a failed save means the
  // user's edits are not persisted even though they are no longer "dirty".
  const blocksNavigation = (status: SaveStatus) => status === 'dirty' || status === 'saving' || status === 'error';

  const confirmNavigation = useCallback(() => {
    const dirty = Object.values(registryRef.current).some((r) => blocksNavigation(r.status));
    if (!dirty) return true;
    return window.confirm('You have unsaved changes. Leave this page anyway?');
  }, []);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      const dirty = Object.values(registryRef.current).some((r) => blocksNavigation(r.status));
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  const value = useMemo(
    () => ({ setStatus, clear, hasUnsaved, isSaving, hasError, confirmNavigation }),
    [setStatus, clear, hasUnsaved, isSaving, hasError, confirmNavigation],
  );

  return <UnsavedChangesContext.Provider value={value}>{children}</UnsavedChangesContext.Provider>;
};

export function useUnsavedChanges(): UnsavedChangesContextValue {
  const ctx = useContext(UnsavedChangesContext);
  if (!ctx) throw new Error('useUnsavedChanges must be used within an UnsavedChangesProvider');
  return ctx;
}
