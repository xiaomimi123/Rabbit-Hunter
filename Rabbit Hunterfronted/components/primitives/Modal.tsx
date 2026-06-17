import { ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Aperture } from './Aperture';

interface Props {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  maxWidth?: string;
}

export function Modal({ open, onClose, title, children, maxWidth = '480px' }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/72 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full bg-bg-base border border-hairline-strong p-6 flex flex-col gap-4"
        style={{ maxWidth }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div className="flex items-center gap-3 pb-3 border-b border-hairline">
            <Aperture size={18} className="text-brass" />
            <h3 className="font-display text-[1.4rem] tracking-tight leading-none">{title}</h3>
          </div>
        )}
        <div>{children}</div>
      </div>
    </div>,
    document.body
  );
}
