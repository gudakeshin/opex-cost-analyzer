import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAudience } from '../../context/AudienceContext';

const CONSULTANT_ONLY = ['/', '/diagnostic', '/skills'];

export const ExecutiveRouteGuard: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isExecutive } = useAudience();
  const location = useLocation();

  if (isExecutive && CONSULTANT_ONLY.includes(location.pathname)) {
    return <Navigate to="/cost-room" replace />;
  }

  return <>{children}</>;
};

export const DefaultRedirect: React.FC = () => {
  const { isExecutive } = useAudience();
  return <Navigate to={isExecutive ? '/cost-room' : '/'} replace />;
};
