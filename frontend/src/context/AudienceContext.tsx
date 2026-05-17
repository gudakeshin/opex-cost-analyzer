import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

export type AudienceMode = 'executive' | 'consultant';

const STORAGE_KEY = 'opex_audience_mode';

interface AudienceContextValue {
  audience: AudienceMode;
  isExecutive: boolean;
  setAudience: (mode: AudienceMode) => void;
  toggleAudience: () => void;
}

const AudienceContext = createContext<AudienceContextValue | null>(null);

function readInitialAudience(): AudienceMode {
  if (typeof window === 'undefined') return 'consultant';
  const params = new URLSearchParams(window.location.search);
  const urlMode = params.get('mode');
  if (urlMode === 'executive' || urlMode === 'consultant') return urlMode;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'executive' || stored === 'consultant') return stored;
  return 'consultant';
}

export function manifestAudienceToMode(audience?: string): AudienceMode | null {
  if (!audience) return null;
  const a = audience.toLowerCase();
  if (a === 'executive' || a === 'cfo' || a === 'c-suite' || a === 'board') return 'executive';
  if (a === 'consultant' || a === 'analyst') return 'consultant';
  return null;
}

export const AudienceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [audience, setAudienceState] = useState<AudienceMode>(readInitialAudience);

  const setAudience = useCallback((mode: AudienceMode) => {
    setAudienceState(mode);
    localStorage.setItem(STORAGE_KEY, mode);
  }, []);

  const toggleAudience = useCallback(() => {
    setAudience(audience === 'executive' ? 'consultant' : 'executive');
  }, [audience, setAudience]);

  const value = useMemo(
    () => ({
      audience,
      isExecutive: audience === 'executive',
      setAudience,
      toggleAudience,
    }),
    [audience, setAudience, toggleAudience],
  );

  return <AudienceContext.Provider value={value}>{children}</AudienceContext.Provider>;
};

export function useAudience(): AudienceContextValue {
  const ctx = useContext(AudienceContext);
  if (!ctx) throw new Error('useAudience must be used within AudienceProvider');
  return ctx;
}
