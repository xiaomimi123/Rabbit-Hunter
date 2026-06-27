import { ReactNode } from 'react';
import { cn } from './cn';

export function SegmentButton({
  active,
  onClick,
  children,
  className,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'rounded-sm px-3 py-1.5 text-xs uppercase tracking-wider2 transition disabled:cursor-not-allowed disabled:opacity-40',
        active
          ? 'bg-brass-soft text-brass border border-brass/40'
          : 'border border-hairline bg-bg-deep text-ivory-70 hover:border-hairline-strong hover:text-ivory',
        className,
      )}
    >
      {children}
    </button>
  );
}
