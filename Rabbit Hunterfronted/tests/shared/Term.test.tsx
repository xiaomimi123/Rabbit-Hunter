import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Term } from '@/components/shared/Term';

describe('Term', () => {
  it('renders children as the visible text', () => {
    render(<Term k="SL">SL</Term>);
    expect(screen.getByText('SL')).toBeInTheDocument();
  });

  it('falls back to plain text for unknown key', () => {
    render(<Term k="UNKNOWN_KEY">hello</Term>);
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('shows tooltip on hover for known key', () => {
    render(<Term k="SL">SL</Term>);
    const term = screen.getByText('SL');
    fireEvent.mouseEnter(term);
    expect(screen.getByText(/止损价/)).toBeInTheDocument();
  });
});
