export function friendlyErrorMessage(raw: string): { title: string; detail: string; recovery?: string } {
  const lower = raw.toLowerCase();
  if (lower.includes('timeout') || lower.includes('408')) {
    return {
      title: 'Analysis took too long',
      detail: 'The server stopped waiting for a response. Try a smaller file or a simpler question.',
      recovery: 'Upload a smaller sample or retry with a focused prompt.',
    };
  }
  if (lower.includes('404') || lower.includes('not found')) {
    return {
      title: 'Data not available yet',
      detail: raw,
      recovery: 'Upload spend data and run analysis first.',
    };
  }
  if (lower.includes('network') || lower.includes('failed to fetch')) {
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
