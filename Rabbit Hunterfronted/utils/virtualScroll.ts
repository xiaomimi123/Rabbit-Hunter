/**
 * 虚拟滚动工具
 * 用于优化大列表渲染性能
 */

export interface VirtualScrollOptions {
  itemHeight: number;
  containerHeight: number;
  overscan?: number; // 额外渲染的项目数（上下各）
}

export interface VirtualScrollResult<T> {
  visibleItems: T[];
  startIndex: number;
  endIndex: number;
  totalHeight: number;
  offsetY: number;
}

/**
 * 计算虚拟滚动可见项
 */
export function calculateVirtualScroll<T>(
  items: T[],
  scrollTop: number,
  options: VirtualScrollOptions
): VirtualScrollResult<T> {
  const { itemHeight, containerHeight, overscan = 3 } = options;

  const totalHeight = items.length * itemHeight;
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(
    items.length - 1,
    Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan
  );

  const visibleItems = items.slice(startIndex, endIndex + 1);
  const offsetY = startIndex * itemHeight;

  return {
    visibleItems,
    startIndex,
    endIndex,
    totalHeight,
    offsetY,
  };
}

/**
 * React Hook: 使用虚拟滚动
 */
import { useState, useEffect, useRef, useCallback } from 'react';

export function useVirtualScroll<T>(
  items: T[],
  options: VirtualScrollOptions
) {
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const result = calculateVirtualScroll(items, scrollTop, options);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // 自动滚动到底部（如果需要）
  useEffect(() => {
    if (containerRef.current) {
      const { totalHeight, containerHeight } = options;
      // 可以添加自动滚动逻辑
    }
  }, [items.length, options]);

  return {
    ...result,
    containerRef,
    handleScroll,
  };
}

