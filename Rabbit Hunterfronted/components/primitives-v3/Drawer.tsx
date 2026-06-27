import { ReactNode, useEffect } from 'react';
import { X } from 'lucide-react';

export function Drawer({
  open, title, subtitle, onClose, children,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" className="absolute inset-0 bg-black/55" onClick={onClose} aria-label="关闭抽屉" />
      <div className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-hairline bg-bg-base p-6 shadow-2xl">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h3 className="text-xl font-semibold text-ivory">{title}</h3>
            {subtitle && <p className="mt-1 text-sm text-ivory-70">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-hairline-strong p-2 text-ivory-70 transition hover:border-brass hover:text-ivory"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
