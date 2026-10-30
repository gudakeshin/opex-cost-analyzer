import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { useConfirm } from './useConfirm';

function Harness({ onResult }: { onResult: (ok: boolean) => void }) {
  const [confirm, dialog] = useConfirm();
  return (
    <>
      <button onClick={async () => onResult(await confirm({ title: 'Remove?', message: 'Really?', danger: true }))}>
        Go
      </button>
      {dialog}
    </>
  );
}

describe('useConfirm', () => {
  it('resolves true when confirmed and false when cancelled', async () => {
    const results: boolean[] = [];
    const user = userEvent.setup();
    render(<Harness onResult={(ok) => results.push(ok)} />);

    await user.click(screen.getByRole('button', { name: 'Go' }));
    expect(screen.getByRole('dialog', { name: 'Remove?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await user.click(screen.getByRole('button', { name: 'Go' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(results).toEqual([true, false]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('treats Escape as a cancel', async () => {
    const results: boolean[] = [];
    const user = userEvent.setup();
    render(<Harness onResult={(ok) => results.push(ok)} />);
    await user.click(screen.getByRole('button', { name: 'Go' }));
    await user.keyboard('{Escape}');
    expect(results).toEqual([false]);
  });
});
