import { useEffect } from 'react';

export type ToastTone = 'info' | 'success' | 'warn' | 'error';

interface Props {
  message: string;
  tone?: ToastTone;
  durationMs?: number;
  onDismiss: () => void;
}

const TONE: Record<ToastTone, string> = {
  info:    'border-ink text-ink bg-ink-soft',
  success: 'border-sage text-sage bg-sage-soft',
  warn:    'border-brass text-brass bg-brass-soft',
  error:   'border-oxblood text-oxblood bg-oxblood-soft',
};

export function Toast({ message, tone = 'info', durationMs = 4000, onDismiss }: Props) {
  useEffect(() => {
    const t = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(t);
  }, [durationMs, onDismiss]);
  return (
    <div className={`border px-4 py-2.5 font-mono text-[0.85rem] ${TONE[tone]}`}>
      <span className="mr-2 opacity-60">▌</span>{message}
    </div>
  );
}
