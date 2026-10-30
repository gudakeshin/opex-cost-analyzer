import React from 'react';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { useAudience } from '../context/AudienceContext';

export const NotFound: React.FC = () => {
  const { isExecutive } = useAudience();
  return (
    <MainLayout title="Page not found">
      <div className="max-w-md py-16">
        <h1 className="text-xl font-semibold text-brand-ink mb-2">We couldn’t find that page</h1>
        <p className="text-sm text-brand-muted mb-6">
          The address may be mistyped, or the page may have moved.
        </p>
        <Link
          to={isExecutive ? '/cost-room' : '/'}
          className="inline-block rounded-lg bg-deloitte-green px-4 py-2 text-sm font-medium text-black hover:opacity-90"
        >
          {isExecutive ? 'Go to the Cost Room' : 'Go to Analysis'}
        </Link>
      </div>
    </MainLayout>
  );
};
