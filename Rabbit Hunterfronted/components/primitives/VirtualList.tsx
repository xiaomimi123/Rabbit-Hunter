import React, { useRef, useState, useEffect } from 'react';

interface Props<T> {
  items: T[];
  itemHeight: number;
  height: number;
  renderItem: (item: T, index: number) => React.ReactNode;
  overscan?: number;
  className?: string;
}

export function VirtualList<T>({ items, itemHeight, height, renderItem, overscan = 4, className = '' }: Props<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);
  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const end = Math.min(items.length, Math.ceil((scrollTop + height) / itemHeight) + overscan);
  const visible = items.slice(start, end);
  return (
    <div ref={ref} className={`overflow-auto ${className}`} style={{ height }}>
      <div style={{ height: items.length * itemHeight, position: 'relative' }}>
        <div style={{ transform: `translateY(${start * itemHeight}px)` }}>
          {visible.map((it, i) => (
            <div key={start + i} style={{ height: itemHeight }}>
              {renderItem(it, start + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
