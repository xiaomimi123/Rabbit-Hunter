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
        'rounded-xl px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40',
        active
          ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/20'
          : 'border border-zinc-800 bg-zinc-950 text-zinc-300 hover:border-zinc-700 hover:text-zinc-100',
        className,
      )}
    >
      {children}
    </button>
  );
}
