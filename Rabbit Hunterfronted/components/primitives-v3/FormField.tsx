import { ReactNode } from 'react';
import { cn } from './cn';

export function FormField({
  label,
  hint,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn('flex flex-col gap-1.5', className)}>
      <span className="text-xs text-zinc-400">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-zinc-500">{hint}</span>}
    </label>
  );
}

export function TextInput({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        'rounded-2xl border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-indigo-500 focus:outline-none',
        className,
      )}
    />
  );
}

export function PrimaryButton({
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        'rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-indigo-900',
        className,
      )}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        'rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-2 text-sm text-zinc-200 transition hover:border-indigo-500 hover:text-indigo-200 disabled:cursor-not-allowed disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  );
}

export function DangerButton({
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        'rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-300 transition hover:border-rose-500 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  );
}
