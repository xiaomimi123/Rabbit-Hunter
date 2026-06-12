import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Card } from '@/components/primitives/Card';
import { Badge } from '@/components/primitives/Badge';
import { ProgressBar } from '@/components/primitives/ProgressBar';
import { Modal } from '@/components/primitives/Modal';
import { NumberInput } from '@/components/primitives/NumberInput';

describe('primitives', () => {
  it('Card renders title and children', () => {
    render(<Card title="Hi"><div>body</div></Card>);
    expect(screen.getByText('Hi')).toBeInTheDocument();
    expect(screen.getByText('body')).toBeInTheDocument();
  });

  it('Badge variant changes background class', () => {
    const { rerender } = render(<Badge variant="long">L</Badge>);
    expect(screen.getByText('L').className).toMatch(/accent-long|bg-/);
    rerender(<Badge variant="short">S</Badge>);
    expect(screen.getByText('S').className).toMatch(/accent-short|bg-/);
  });

  it('ProgressBar clamps value 0-100 and shows label', () => {
    render(<ProgressBar value={120} label="loading" />);
    const bar = screen.getByRole('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('100');
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('Modal shows when open, hides when not', () => {
    const { rerender } = render(
      <Modal open={false} onClose={() => {}}><div>content</div></Modal>
    );
    expect(screen.queryByText('content')).not.toBeInTheDocument();
    rerender(<Modal open onClose={() => {}}><div>content</div></Modal>);
    expect(screen.getByText('content')).toBeInTheDocument();
  });

  it('NumberInput respects min/max and calls onChange', async () => {
    const user = userEvent.setup();
    let val = 50;
    const onChange = (v: number) => { val = v; };
    render(<NumberInput value={50} min={0} max={100} step={1} onChange={onChange} />);
    const input = screen.getByRole('spinbutton') as HTMLInputElement;
    await user.clear(input);
    await user.type(input, '75');
    expect(val).toBe(75);
  });
});
