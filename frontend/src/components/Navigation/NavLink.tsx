import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { isNavActive } from '../../utils/navPath';

interface NavLinkProps {
  to: string;
  label: string;
  icon?: React.ReactNode;
  collapsed?: boolean;
  onNavigate?: () => void;
  badge?: number;
}

export const NavLink: React.FC<NavLinkProps> = ({
  to,
  label,
  icon,
  collapsed = false,
  onNavigate,
  badge = 0,
}) => {
  const location = useLocation();
  const active = isNavActive(location.pathname, to);

  return (
    <Link
      to={to}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      title={collapsed ? label : undefined}
      className={`
        group relative flex items-center gap-3 rounded-sm
        transition-colors duration-150
        border-l-4
        ${active
          ? 'border-deloitte-green bg-[#f7f7f5] text-black font-semibold'
          : 'border-transparent text-[#53565a] hover:bg-[#f7f7f5] hover:text-black font-medium'
        }
        ${collapsed ? 'justify-center px-2 py-3' : 'px-3 py-2.5'}
      `}
    >
      {icon && (
        <span
          className={`w-5 h-5 flex-shrink-0 ${active ? 'text-deloitte-green' : 'text-[#53565a] group-hover:text-black'}`}
        >
          {icon}
        </span>
      )}
      {!collapsed && (
        <>
          <span className="flex-1 text-sm leading-snug">{label}</span>
          {badge > 0 && (
            <span className="min-w-[1.25rem] h-5 px-1.5 rounded-full bg-black text-white text-xs font-bold flex items-center justify-center">
              {badge > 99 ? '99+' : badge}
            </span>
          )}
        </>
      )}
      {collapsed && active && (
        <span
          className="absolute right-1 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-deloitte-green"
          aria-hidden
        />
      )}
    </Link>
  );
};
