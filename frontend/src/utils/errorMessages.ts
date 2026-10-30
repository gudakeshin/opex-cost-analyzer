export interface FriendlyError {
  title: string;
  detail: string;
  recovery?: string;
}

// Match whole tokens rather than substrings, so "…timeout_seconds", "Engagement 4040" or "network opex"
// in an unrelated message are not mistaken for a timeout, a 404 or a connection problem.
const TIMEOUT = /\b(timed? ?out|timeout|408)\b/i;
const HTTP_404 = /\b(status code|http|error)\s*404\b|^404\b/i;
const NOT_FOUND = /\bnot found\b/i;
const NETWORK = /\bnetwork error\b|failed to fetch|\bnetwork request failed\b|\bERR_NETWORK\b/i;

export function friendlyErrorMessage(raw: string): FriendlyError {
  if (TIMEOUT.test(raw)) {
    return {
      title: 'This took too long',
      detail: 'The server stopped waiting for a response.',
      recovery: 'Retry, or try a smaller file or a more focused question.',
    };
  }
  // Server "not found" messages are short ("Session not found"); long text that merely contains the
  // phrase is shown as a generic error with its full detail.
  if (HTTP_404.test(raw) || (NOT_FOUND.test(raw) && raw.length <= 160)) {
    return {
      title: 'Data not available yet',
      detail: raw,
      recovery: 'Upload spend data and run analysis first.',
    };
  }
  if (NETWORK.test(raw)) {
    return {
      title: 'Connection problem',
      detail: 'We could not reach the server. Check your connection and try again.',
      recovery: 'Retry in a few seconds.',
    };
  }
  return {
    title: 'Something went wrong',
    detail: raw,
    recovery: 'If this persists, start a new session or contact your platform admin.',
  };
}
