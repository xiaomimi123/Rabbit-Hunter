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
      <span className="text-[10px] uppercase tracking-wider2 text-ivory-40">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-ivory-40">{hint}</span>}
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
        'rounded-md border border-hairline-strong bg-bg-deep px-3 py-2 font-mono text-sm text-ivory placeholder:text-ivory-40 focus:border-brass focus:outline-none transition',
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
        'rounded-md border border-brass bg-brass-soft px-4 py-2 text-sm font-medium uppercase tracking-wider2 text-brass transition hover:bg-brass hover:text-bg-base disabled:cursor-not-allowed disabled:opacity-40',
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
        'rounded-md border border-hairline-strong bg-bg-deep px-4 py-2 text-sm text-ivory-70 transition hover:border-brass hover:text-ivory disabled:cursor-not-allowed disabled:opacity-40',
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
        'rounded-md border border-oxblood/40 bg-oxblood-soft px-4 py-2 text-sm text-oxblood transition hover:border-oxblood hover:bg-oxblood hover:text-ivory disabled:cursor-not-allowed disabled:opacity-40',
        className,
      )}
    >
      {children}
    </button>
  );
}
