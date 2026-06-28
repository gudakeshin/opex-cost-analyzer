import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

const navigateMock = vi.fn();
const resumeSessionMock = vi.fn();

vi.mock('../hooks/useApi', () => ({
  apiGet: vi.fn().mockResolvedValue([
    {
      session_id: 'sess-1',
      engagement_id: 'eng-1',
      company_name: 'Acme',
      industry: 'technology',
      currency: 'INR',
      annual_revenue: 10000000,
      file_count: 2,
      has_analysis: true,
    },
  ]),
  getApiErrorMessage: vi.fn().mockReturnValue('error'),
}));

vi.mock('react-router-dom', async (orig) => {
  const actual = await orig<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../components/Layout/MainLayout', () => ({
  MainLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../context/SessionContext', () => ({
  useSession: () => ({
    sessionId: null,
    resumeSession: resumeSessionMock,
  }),
}));

import { SessionHistory } from '../pages/SessionHistory';

test('resuming a session keeps engagement in sync', async () => {
  render(
    <MemoryRouter>
      <SessionHistory />
    </MemoryRouter>,
  );

  const resumeButton = await screen.findByRole('button', { name: /resume/i });
  fireEvent.click(resumeButton);

  await waitFor(() => {
    expect(resumeSessionMock).toHaveBeenCalledWith('sess-1', 'eng-1');
    expect(navigateMock).toHaveBeenCalledWith('/');
  });
});
