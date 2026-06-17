import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Aperture } from '@/components/primitives/Aperture';

describe('Aperture', () => {
  it('renders an svg with 3 concentric circles + 4 crosshair lines', () => {
    const { container } = render(<Aperture size={32} />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute('width')).toBe('32');
    expect(svg!.getAttribute('height')).toBe('32');
    expect(container.querySelectorAll('circle').length).toBe(3);
    expect(container.querySelectorAll('line').length).toBe(4);
  });

  it('applies fast sweep animation when rotate=true', () => {
    const { container } = render(<Aperture size={24} rotate />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('class') ?? '').toContain('animate-aperture-sweep-fast');
  });

  it('applies slow sweep animation when rotate="slow"', () => {
    const { container } = render(<Aperture size={24} rotate="slow" />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('class') ?? '').toContain('animate-aperture-sweep-slow');
  });

  it('does not animate by default', () => {
    const { container } = render(<Aperture size={20} />);
    const svg = container.querySelector('svg');
    const cls = svg?.getAttribute('class') ?? '';
    expect(cls).not.toContain('animate-aperture-sweep');
  });

  it('passes through className', () => {
    const { container } = render(<Aperture size={20} className="text-brass" />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('class') ?? '').toContain('text-brass');
  });

  it('defaults size to 24 if not provided', () => {
    const { container } = render(<Aperture />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('width')).toBe('24');
  });
});
