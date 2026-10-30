import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Input } from './Input';

describe('Input', () => {
  it('links label, hint and error, and marks the field invalid', () => {
    render(<Input label="Revenue" hint="In crore" error="Required" />);
    const input = screen.getByLabelText('Revenue');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const describedBy = (input.getAttribute('aria-describedby') ?? '').split(' ');
    expect(describedBy).toHaveLength(2);
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
    expect(screen.getByText('In crore')).toBeInTheDocument();
  });

  it('gives two same-label inputs distinct ids', () => {
    render(
      <>
        <Input label="Name" />
        <Input label="Name" />
      </>,
    );
    const [a, b] = screen.getAllByLabelText('Name');
    expect(a.id).not.toEqual(b.id);
  });
});
