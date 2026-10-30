import { describe, expect, it } from 'vitest';
import { friendlyErrorMessage } from './errorMessages';

describe('friendlyErrorMessage', () => {
  it('recognises real timeouts, 404s and connection problems', () => {
    expect(friendlyErrorMessage('Request failed with status code 408').title).toBe('This took too long');
    expect(friendlyErrorMessage('timeout of 30000ms exceeded').title).toBe('This took too long');
    expect(friendlyErrorMessage('Request failed with status code 404').title).toBe('Data not available yet');
    expect(friendlyErrorMessage('Session not found').title).toBe('Data not available yet');
    expect(friendlyErrorMessage('Network Error').title).toBe('Connection problem');
    expect(friendlyErrorMessage('TypeError: Failed to fetch').title).toBe('Connection problem');
  });

  it('does not misclassify messages that only contain look-alike text', () => {
    expect(friendlyErrorMessage('Invalid setting LLM_SYNTHESIS_TIMEOUT_SECONDS=abc').title).toBe('Something went wrong');
    expect(friendlyErrorMessage('Engagement 4040 has 3 documents').title).toBe('Something went wrong');
    expect(friendlyErrorMessage('Category "network opex" is empty').title).toBe('Something went wrong');
    const long = `Validation failed: ${'x'.repeat(200)} (field not found)`;
    expect(friendlyErrorMessage(long).title).toBe('Something went wrong');
  });
});
