import React, { useEffect } from 'react';

export type ToastTone = 'info' | 'success' | 'warn' | 'error';

interface Props {
  message: string;
  tone?: ToastTone;
  durationMs?: number;
  onDismiss: () => void;
}

const TONE: Record<ToastTone, string> = {
  info: 'border-accent-info/40 bg-accent-info/10 text-accent-info',
  success: 'border-accent-long/40 bg-accent-long/10 text-accent-long',
  warn: 'border-accent-warn/40 bg-accent-warn/10 text-accent-warn',
  error: 'border-accent-short/40 bg-accent-short/10 text-accent-short',
};

export function Toast({ message, tone = 'info', durationMs = 4000, onDismiss }: Props) {
  useEffect(() => {
    const t = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(t);
  }, [durationMs, onDismiss]);
  return (
    <div className={`rounded-md border px-3 py-2 text-sm shadow-md ${TONE[tone]}`}>
      {message}
    </div>
  );
}
