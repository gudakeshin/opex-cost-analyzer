import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { RecommendedBadge } from './RecommendedBadge';

function renderBadge(props: {
  label: string;
  matches: boolean;
  onApply?: () => void;
  changeLink?: string;
}) {
  return render(
    <MemoryRouter>
      <RecommendedBadge {...props} />
    </MemoryRouter>,
  );
}

describe('RecommendedBadge', () => {
  it('shows recommendation label', () => {
    renderBadge({ label: 'Belrise', matches: true });
    expect(screen.getByText(/Recommended from your documents/)).toBeInTheDocument();
    expect(screen.getByText('Belrise')).toBeInTheDocument();
  });

  it('shows Use recommended when selection differs', async () => {
    const onApply = vi.fn();
    renderBadge({ label: 'Belrise', matches: false, onApply });
    await userEvent.click(screen.getByRole('button', { name: /Use recommended/i }));
    expect(onApply).toHaveBeenCalledOnce();
  });

  it('hides Use recommended when selection matches', () => {
    renderBadge({ label: 'Belrise', matches: true, onApply: vi.fn() });
    expect(screen.queryByRole('button', { name: /Use recommended/i })).toBeNull();
  });

  it('links to Diagnostic for changes', () => {
    renderBadge({ label: 'Belrise', matches: false, changeLink: '/diagnostic' });
    const link = screen.getByRole('link', { name: /Change in Diagnostic/i });
    expect(link).toHaveAttribute('href', '/diagnostic');
  });
});
