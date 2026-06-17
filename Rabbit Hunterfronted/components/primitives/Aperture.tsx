import { CSSProperties } from 'react';

interface ApertureProps {
  size?: number;
  rotate?: boolean | 'slow';
  className?: string;
  style?: CSSProperties;
}

export function Aperture({ size = 24, rotate = false, className = '', style }: ApertureProps) {
  const sweep =
    rotate === 'slow'
      ? 'animate-aperture-sweep-slow'
      : rotate
        ? 'animate-aperture-sweep-fast'
        : '';

  const cls = `${sweep} ${className}`.trim();

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      stroke="currentColor"
      strokeWidth="0.7"
      className={cls}
      style={style}
      aria-hidden="true"
    >
      <circle cx="20" cy="20" r="18" />
      <circle cx="20" cy="20" r="12" />
      <circle cx="20" cy="20" r="6" />
      <line x1="20" y1="0" x2="20" y2="6" strokeWidth="1.2" />
      <line x1="20" y1="34" x2="20" y2="40" strokeWidth="1.2" />
      <line x1="0" y1="20" x2="6" y2="20" strokeWidth="1.2" />
      <line x1="34" y1="20" x2="40" y2="20" strokeWidth="1.2" />
    </svg>
  );
}
