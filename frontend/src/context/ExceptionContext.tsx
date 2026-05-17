import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ExceptionItem } from '../utils/exceptions';

interface ExceptionContextValue {
  items: ExceptionItem[];
  count: number;
  setItems: (items: ExceptionItem[]) => void;
}

const ExceptionContext = createContext<ExceptionContextValue | null>(null);

export const ExceptionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItemsState] = useState<ExceptionItem[]>([]);
  const setItems = useCallback((next: ExceptionItem[]) => setItemsState(next), []);
  const value = useMemo(
    () => ({ items, count: items.length, setItems }),
    [items, setItems],
  );
  return <ExceptionContext.Provider value={value}>{children}</ExceptionContext.Provider>;
};

export function useExceptions(): ExceptionContextValue {
  const ctx = useContext(ExceptionContext);
  if (!ctx) {
    return {
      items: [],
      count: 0,
      setItems: () => undefined,
    };
  }
  return ctx;
}
