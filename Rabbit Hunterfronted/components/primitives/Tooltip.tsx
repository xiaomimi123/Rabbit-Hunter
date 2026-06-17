import { ReactNode, useState, useRef, useEffect } from 'react';

interface Props {
  content: ReactNode;
  children: ReactNode;
  className?: string;
  maxWidth?: number;
}

export function Tooltip({ content, children, className = '', maxWidth = 320 }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const [placement, setPlacement] = useState<'top' | 'bottom'>('top');

  useEffect(() => {
    if (!open || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    setPlacement(rect.top < 80 ? 'bottom' : 'top');
  }, [open]);

  return (
    <span
      ref={ref}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      className={`relative inline-block ${className}`}
      tabIndex={0}
    >
      {children}
      {open && (
        <span
          className={`absolute z-40 border border-hairline-strong bg-bg-elevated px-3 py-2 font-body italic text-[0.78rem] text-ivory-70 shadow-xl ${
            placement === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'
          } left-1/2 -translate-x-1/2 pointer-events-none whitespace-normal leading-relaxed`}
          style={{ maxWidth, minWidth: 180 }}
        >
          {content}
        </span>
      )}
    </span>
  );
}
