import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { NavLink } from './NavLink';
import { useSidebar } from '../../context/SidebarContext';
import { useAudience } from '../../context/AudienceContext';
import { useSession } from '../../context/SessionContext';
import { ChartIcon, SearchIcon, CostRoomIcon, GuidebookIcon, DocumentsIcon } from './NavIcons';
import { useExceptions } from '../../context/ExceptionContext';
import { useUnsavedChanges } from '../../context/UnsavedChangesContext';
import { DeloitteLogo } from '../Brand/DeloitteLogo';
import { isClientEngagementReady } from '../../utils/engagement';
import { isNavActive } from '../../utils/navPath';

const CONSULTANT_LINKS = [
  { to: '/', label: 'Analysis', icon: <ChartIcon /> },
  { to: '/diagnostic', label: 'Diagnostic', icon: <SearchIcon /> },
  { to: '/workbench', label: 'Workbench', icon: <WorkbenchIcon /> },
  { to: '/cost-room', label: 'Cost Room', icon: <CostRoomIcon /> },
  { to: '/benchmarks', label: 'Benchmarks', icon: <BenchmarksIcon /> },
  { to: '/sector-packs', label: 'Pack Studio', icon: <PackStudioIcon /> },
  { to: '/skills', label: 'Skills', icon: <SkillsIcon /> },
  { to: '/documents', label: 'Documents', icon: <DocumentsIcon /> },
  { to: '/guidebook', label: 'Guidebook', icon: <GuidebookIcon /> },
  { to: '/history', label: 'History', icon: <HistoryIcon /> },
];

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { collapsed, mobileOpen, isMobile, toggleCollapsed, setMobileOpen } = useSidebar();
  const { isExecutive, audience, setAudience } = useAudience();
  const { count: exceptionCount } = useExceptions();
  const { engagement, hasAnalysis } = useSession();
  const { confirmNavigation } = useUnsavedChanges();
  const showLabels = !collapsed || isMobile;
  const executiveReady = isClientEngagementReady(hasAnalysis, engagement.company_name);

  const activeLink = CONSULTANT_LINKS.find((link) => isNavActive(location.pathname, link.to));

  if (isExecutive) return null;

  const handleExecutiveToggle = () => {
    if (!executiveReady) return;
    // Confirm before switching audience so a cancelled navigation doesn't
    // leave the app toggled to executive mode on the current page.
    if (!confirmNavigation()) return;
    setAudience('executive');
    navigate('/cost-room');
  };

  return (
    <>
      {isMobile && mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 bg-black/40 z-40"
          aria-label="Close menu"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        className={`
          sidebar fixed left-0 top-0 h-screen z-50
          bg-white border-r border-brand-border
          flex flex-col
          transition-all duration-300 ease-in-out
          ${isMobile
            ? `w-sidebar-expanded ${mobileOpen ? 'open translate-x-0' : '-translate-x-full'}`
            : collapsed ? 'w-sidebar-collapsed' : 'w-sidebar-expanded'}
        `}
      >
        <div className="flex items-center justify-between p-4 border-b border-brand-border">
          {showLabels ? (
            <DeloitteLogo />
          ) : (
            <DeloitteLogo variant="mark" />
          )}
          <button
            type="button"
            onClick={toggleCollapsed}
            className={`p-2 hover:bg-brand-surface-muted rounded-sm transition-colors text-brand-muted ${!showLabels ? 'mx-auto' : 'ml-auto'}`}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed && !isMobile ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </button>
        </div>

        {collapsed && !isMobile && activeLink && (
          <p
            className="px-2 py-2 text-[10px] font-semibold uppercase tracking-wider text-center text-deloitte-green border-b border-brand-border leading-tight"
            title={activeLink.label}
          >
            {activeLink.label.split(' ')[0]}
          </p>
        )}

        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
          {CONSULTANT_LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              label={link.label}
              icon={link.icon}
              collapsed={!showLabels}
              onNavigate={isMobile ? () => setMobileOpen(false) : undefined}
              badge={
                link.to === '/cost-room' || link.to === '/'
                  ? exceptionCount
                  : 0
              }
            />
          ))}
        </nav>

        {showLabels && (
          <div className="p-4 border-t border-brand-border space-y-3">
            <button
              type="button"
              onClick={handleExecutiveToggle}
              disabled={!executiveReady}
              title={
                executiveReady
                  ? 'Open executive Cost Room for this client'
                  : 'Run analysis first to enable executive view'
              }
              className={`w-full text-left text-xs px-3 py-2 rounded-sm border ${
                executiveReady
                  ? 'border-brand-border hover:bg-brand-surface-muted text-black'
                  : 'border-brand-border/60 text-brand-muted cursor-not-allowed opacity-70'
              }`}
            >
              {audience === 'executive' ? 'Consultant view' : 'Executive view'}
              {!executiveReady && (
                <span className="block mt-1 text-[10px]">Available after analysis</span>
              )}
            </button>
            <p className="text-[10px] text-brand-muted leading-snug">
              OpEx Intelligence Platform
            </p>
          </div>
        )}
      </aside>
    </>
  );
};

function HistoryIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function WorkbenchIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M11 4a2 2 0 114 0v1h2a1 1 0 011 1v2h1a2 2 0 110 4h-1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6H3a2 2 0 110-4h1V6a1 1 0 011-1h2V4z" />
    </svg>
  );
}

function SkillsIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function BenchmarksIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}

function PackStudioIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
    </svg>
  );
}

function ChevronLeftIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 0l-7 7 7 7" />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
    </svg>
  );
}
