/**
 * Confirm dialog for money-moving actions.
 * Replaces native window.confirm() — shows full context (symbol/side/notional/PnL)
 * so the user can't blindly click through.
 */

import React, { useEffect, useRef } from 'react';
import { X, AlertTriangle } from 'lucide-react';

interface ConfirmDetail {
  label: string;
  value: React.ReactNode;
  tone?: 'neutral' | 'bull' | 'bear' | 'warn';
}

interface ConfirmModalProps {
  open: boolean;
  title: string;
  description?: string;
  details?: ConfirmDetail[];
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  open, title, description, details, confirmLabel = '确认',
  cancelLabel = '取消', destructive, loading, onConfirm, onCancel,
}) => {
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null);

  // Trap basic focus + ESC to close
  useEffect(() => {
    if (!open) return;
    confirmBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel, loading]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 animate-fade-in"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={loading ? undefined : onCancel}
    >
      <div
        className="surface w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            {destructive && (
              <AlertTriangle size={16} className="text-bear shrink-0 mt-0.5" />
            )}
            <h3 className="text-[15px] font-medium text-text-primary tracking-tight">
              {title}
            </h3>
          </div>
          {!loading && (
            <button
              onClick={onCancel}
              className="text-text-muted hover:text-text-primary transition-colors"
              aria-label="关闭"
            >
              <X size={16} />
            </button>
          )}
        </div>

        {description && (
          <p className="text-[13px] text-text-secondary leading-relaxed mb-3">
            {description}
          </p>
        )}

        {details && details.length > 0 && (
          <div className="my-4 space-y-1.5 py-3 border-y border-terminal-border">
            {details.map((d) => (
              <div key={d.label} className="flex items-center justify-between text-[12px]">
                <span className="text-text-muted">{d.label}</span>
                <span className={
                  d.tone === 'bull' ? 'num text-bull' :
                  d.tone === 'bear' ? 'num text-bear' :
                  d.tone === 'warn' ? 'num text-warn' :
                  'num text-text-primary'
                }>
                  {d.value}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 mt-5">
          <button
            onClick={onCancel}
            disabled={loading}
            className="btn-ghost"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={onConfirm}
            disabled={loading}
            className={destructive ? 'btn-bear' : 'btn-primary'}
          >
            {loading ? '处理中…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
