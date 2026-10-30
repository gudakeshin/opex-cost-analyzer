import { act, render, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createTestQueryClient } from '../test/queryClient';

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

  const queryClient = createTestQueryClient();
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <Consumer />
        </SessionProvider>
      </QueryClientProvider>,
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

  it('converges concurrent ensureSessionForEngagement calls into a single engagement/session pair', async () => {
    apiGet.mockImplementation((url: string) => {
      if (url.endsWith('/status')) {
        return Promise.resolve({ session_exists: true, has_analysis: false });
      }
      if (url.includes('/manifest')) {
        return Promise.resolve({
          engagement_id: 'eng-new',
          company_name: 'New engagement',
          industry: '',
          currency: 'INR',
        });
      }
      // latestAnalyzedSessionId's listing — nothing analyzed yet.
      if (url === '/api/v1/sessions') return Promise.resolve([]);
      if (/\/engagements\/[^/]+$/.test(url)) {
        return Promise.resolve({ company_name: 'New engagement', industry: '', currency: 'INR' });
      }
      return Promise.resolve({});
    });
    apiPost.mockImplementation((url: string) => {
      if (url === '/api/v1/engagements') {
        return Promise.resolve({ engagement_id: 'eng-new' });
      }
      if (url === '/api/v1/sessions') {
        return Promise.resolve({
          session_id: 'sess-new',
          engagement_id: 'eng-new',
          company_name: 'New engagement',
          industry: '',
          currency: 'INR',
        });
      }
      return Promise.resolve({});
    });

    const queryClient = createTestQueryClient();
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SessionProvider>
            <Consumer />
          </SessionProvider>
        </QueryClientProvider>,
      );
    });

    // Simulate two overlapping callers (e.g. an effect re-firing before the
    // first ensure resolves) racing on a fresh session/engagement.
    let first: string;
    let second: string;
    await act(async () => {
      [first, second] = await Promise.all([
        ctx.ensureSessionForEngagement(),
        ctx.ensureSessionForEngagement(),
      ]);
    });

    expect(apiPost.mock.calls.filter(([url]) => url === '/api/v1/engagements')).toHaveLength(1);
    expect(apiPost.mock.calls.filter(([url]) => url === '/api/v1/sessions')).toHaveLength(1);
    expect(first!).toBe('sess-new');
    expect(second!).toBe('sess-new');
    expect(ctx.sessionId).toBe('sess-new');
    expect(ctx.engagementId).toBe('eng-new');
  });

  it('merges an explicit-target call that arrives before the in-flight call has resolved its own target', async () => {
    // Deferred promises let us pause createEngagement() mid-flight, right
    // after it has committed engagementId to state but before
    // ensureSessionForEngagement's own bookkeeping has learned that target —
    // the exact window where an effect re-firing off the new engagementId
    // used to race past the guard and create a second session.
    let resolveEngagementPost!: (v: { engagement_id: string }) => void;
    const engagementPost = new Promise<{ engagement_id: string }>((res) => {
      resolveEngagementPost = res;
    });
    let resolveEngagementDetail!: (v: {
      company_name: string;
      industry: string;
      currency: string;
    }) => void;
    const engagementDetail = new Promise<{
      company_name: string;
      industry: string;
      currency: string;
    }>((res) => {
      resolveEngagementDetail = res;
    });

    apiGet.mockImplementation((url: string) => {
      if (url.endsWith('/status')) {
        return Promise.resolve({ session_exists: true, has_analysis: false });
      }
      if (url.includes('/manifest')) {
        return Promise.resolve({
          engagement_id: 'eng-race',
          company_name: 'New engagement',
          industry: '',
          currency: 'INR',
        });
      }
      if (url === '/api/v1/sessions') return Promise.resolve([]);
      if (/\/engagements\/[^/]+$/.test(url)) return engagementDetail;
      return Promise.resolve({});
    });
    apiPost.mockImplementation((url: string) => {
      if (url === '/api/v1/engagements') return engagementPost;
      if (url === '/api/v1/sessions') {
        return Promise.resolve({
          session_id: 'sess-race',
          engagement_id: 'eng-race',
          company_name: 'New engagement',
          industry: '',
          currency: 'INR',
        });
      }
      return Promise.resolve({});
    });

    const queryClient = createTestQueryClient();
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <SessionProvider>
            <Consumer />
          </SessionProvider>
        </QueryClientProvider>,
      );
    });

    let callA: Promise<string>;
    act(() => {
      callA = ctx.ensureSessionForEngagement();
    });
    resolveEngagementPost({ engagement_id: 'eng-race' });

    // Once this resolves, createEngagement has already called
    // setEngagementIdState('eng-race') and is now blocked inside
    // refreshEngagementMeta awaiting the (still-unresolved) detail fetch.
    await waitFor(() => {
      expect(ctx.engagementId).toBe('eng-race');
    });

    let callC: Promise<string>;
    act(() => {
      callC = ctx.ensureSessionForEngagement('eng-race');
    });
    resolveEngagementDetail({ company_name: 'New engagement', industry: '', currency: 'INR' });

    const [resultA, resultC] = await act(async () => Promise.all([callA, callC]));

    expect(apiPost.mock.calls.filter(([url]) => url === '/api/v1/engagements')).toHaveLength(1);
    expect(apiPost.mock.calls.filter(([url]) => url === '/api/v1/sessions')).toHaveLength(1);
    expect(resultA).toBe('sess-race');
    expect(resultC).toBe('sess-race');
  });
});
