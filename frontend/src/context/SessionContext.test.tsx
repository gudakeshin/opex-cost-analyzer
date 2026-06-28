import { act, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiDelete = vi.fn();

vi.mock('../hooks/useApi', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiDelete: (...args: unknown[]) => apiDelete(...args),
}));

// Stable reference: a fresh object each render would make refreshEngagement
// unstable and trigger an effect loop in the provider.
const audienceValue = { setAudience: vi.fn() };
vi.mock('./AudienceContext', () => ({
  useAudience: () => audienceValue,
  manifestAudienceToMode: () => null,
}));

import { SessionProvider, useSession } from './SessionContext';

type Ctx = ReturnType<typeof useSession>;
let ctx: Ctx;

function Consumer() {
  ctx = useSession();
  return null;
}

function routeApiGet(url: string) {
  if (url.endsWith('/status')) {
    return Promise.resolve({ session_exists: true, has_analysis: true });
  }
  if (url.includes('/manifest')) {
    return Promise.resolve({
      engagement_id: 'eng-A',
      company_name: 'Acme A',
      industry: 'it_ites',
      currency: 'INR',
      audience: 'consultant',
      deep_research_summary: 'Deep research for engagement A',
    });
  }
  // GET /api/v1/sessions/{sid} -> analysis payload
  if (/\/sessions\/[^/]+$/.test(url)) {
    return Promise.resolve({
      session_id: 'sess-A',
      company_name: 'Acme A',
      industry: 'it_ites',
      spend_base_revision: 1,
    });
  }
  // GET /api/v1/engagements/{eid} -> engagement detail
  if (/\/engagements\/[^/]+$/.test(url)) {
    return Promise.resolve({ company_name: 'Acme A', industry: 'it_ites', currency: 'INR' });
  }
  return Promise.resolve({});
}

async function renderSeeded() {
  localStorage.setItem('opex_session_id', 'sess-A');
  localStorage.setItem('opex_engagement_id', 'eng-A');
  apiGet.mockImplementation((url: string) => routeApiGet(url));

  await act(async () => {
    render(
      <SessionProvider>
        <Consumer />
      </SessionProvider>,
    );
  });

  // Mount effects load the manifest (deep research summary). Explicitly load
  // analysis so all three derived fields are populated for engagement A.
  await act(async () => {
    await ctx.refreshSessionAnalysis();
  });

  await waitFor(() => {
    expect(ctx.sessionAnalysis).not.toBeNull();
    expect(ctx.deepResearchSummary).toBe('Deep research for engagement A');
    expect(ctx.hasAnalysis).toBe(true);
  });
}

describe('SessionContext derived-state reset', () => {
  beforeEach(() => {
    localStorage.clear();
    apiGet.mockReset();
    apiPost.mockReset();
    apiDelete.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('clears analysis and deep research when a new engagement is created', async () => {
    await renderSeeded();
    apiPost.mockResolvedValue({ engagement_id: 'eng-B' });

    await act(async () => {
      await ctx.createEngagement();
    });

    expect(ctx.sessionId).toBeNull();
    expect(ctx.sessionAnalysis).toBeNull();
    expect(ctx.deepResearchSummary).toBeNull();
    expect(ctx.hasAnalysis).toBe(false);
  });

  it('clears analysis and deep research when switching engagements', async () => {
    await renderSeeded();

    await act(async () => {
      ctx.setEngagementId('eng-B');
    });

    expect(ctx.sessionId).toBeNull();
    expect(ctx.sessionAnalysis).toBeNull();
    expect(ctx.deepResearchSummary).toBeNull();
    expect(ctx.hasAnalysis).toBe(false);
  });

  it('clears analysis and deep research when the active engagement is deleted', async () => {
    await renderSeeded();
    apiDelete.mockResolvedValue({});

    await act(async () => {
      await ctx.deleteEngagement('eng-A');
    });

    expect(ctx.sessionId).toBeNull();
    expect(ctx.sessionAnalysis).toBeNull();
    expect(ctx.deepResearchSummary).toBeNull();
    expect(ctx.hasAnalysis).toBe(false);
  });
});
