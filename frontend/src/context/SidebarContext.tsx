import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

const MOBILE_BREAKPOINT = 768;
const EXPANDED_WIDTH = '240px';
const COLLAPSED_WIDTH = '60px';

interface SidebarContextValue {
  collapsed: boolean;
  mobileOpen: boolean;
  isMobile: boolean;
  sidebarWidth: string;
  toggleCollapsed: () => void;
  setMobileOpen: (open: boolean) => void;
}

const SidebarContext = createContext<SidebarContextValue | null>(null);

export const SidebarProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isMobile, setIsMobile] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const sync = () => {
      const mobile = mq.matches;
      setIsMobile(mobile);
      if (mobile) {
        setCollapsed(true);
        setMobileOpen(false);
      }
    };
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  const toggleCollapsed = useCallback(() => {
    if (isMobile) {
      setMobileOpen((o) => !o);
    } else {
      setCollapsed((c) => !c);
    }
  }, [isMobile]);

  const sidebarWidth = useMemo(() => {
    if (isMobile) return '0px';
    return collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH;
  }, [collapsed, isMobile]);

  const value = useMemo(
    () => ({
      collapsed,
      mobileOpen,
      isMobile,
      sidebarWidth,
      toggleCollapsed,
      setMobileOpen,
    }),
    [collapsed, mobileOpen, isMobile, sidebarWidth, toggleCollapsed],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
};

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext);
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider');
  return ctx;
}
