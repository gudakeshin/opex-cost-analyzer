import React, { useEffect } from 'react';
import { Sidebar } from '../Navigation/Sidebar';
import { ThemeToggle } from '../Navigation/ThemeToggle';
import { useSidebar } from '../../context/SidebarContext';
import { useAudience } from '../../context/AudienceContext';

interface MainLayoutProps {
  children: React.ReactNode;
  title?: string;
  headerExtra?: React.ReactNode;
  variant?: 'default' | 'executive';
  hideHeader?: boolean;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  children,
  title,
  headerExtra,
  variant,
  hideHeader = false,
}) => {
  const { sidebarWidth, isMobile, toggleCollapsed } = useSidebar();
  const { isExecutive } = useAudience();
  const executive = variant === 'executive' || isExecutive;

  useEffect(() => {
    if (executive) document.documentElement.classList.remove('dark');
  }, [executive]);

  if (executive) {
    return (
      <div className="min-h-screen executive-shell bg-brand-surface">
        <div className="p-4 md:p-6 lg:p-8 max-w-[1600px] mx-auto">{children}</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main
        className="flex-1 min-h-screen bg-brand-surface transition-[margin] duration-300"
        style={{ marginLeft: sidebarWidth }}
      >
        {!hideHeader && (
          <header className="sticky top-0 z-30 bg-white border-b border-brand-border shadow-sm">
            <div className="flex items-center justify-between px-4 md:px-6 py-4 gap-4">
              <div className="flex items-center gap-3 min-w-0">
                {isMobile && (
                  <button
                    type="button"
                    onClick={toggleCollapsed}
                    className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 shrink-0"
                    aria-label="Open menu"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                  </button>
                )}
                {title && (
                  <h1 className="text-2xl font-bold font-sans text-brand-ink tracking-tight truncate">{title}</h1>
                )}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {headerExtra}
                <ThemeToggle />
              </div>
            </div>
          </header>
        )}
        <div className="p-4 md:p-6">{children}</div>
      </main>
    </div>
  );
};
