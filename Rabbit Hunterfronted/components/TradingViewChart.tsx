/**
 * React 组件包装: TradingView Lightweight Charts
 * 用于在 React 中使用图表
 */

import React, { useEffect, useRef } from 'react';
import { TradingViewChartManager } from '../services/tradingViewChart';
import { CandlestickData } from 'lightweight-charts';

export interface TradingViewChartComponentProps {
  symbol?: string;
  chartId?: string; // 兼容 OrderPage 使用的 chartId
  data: CandlestickData[];
  width?: number;
  height?: number;
  priceLines?: Array<{
    price: number;
    color?: string;
    title?: string;
  }>;
  markers?: Array<{
    time: number;
    position: 'aboveBar' | 'belowBar';
    color: string;
    shape: 'circle' | 'square' | 'arrowUp' | 'arrowDown';
    text?: string;
  }>;
  options?: any; // 兼容 OrderPage 使用的 options
  onChartReady?: (manager: TradingViewChartManager) => void;
}

/**
 * TradingView 图表 React 组件
 */
export const TradingViewChartComponent = React.forwardRef<
  TradingViewChartManager | null,
  TradingViewChartComponentProps
>(
  (
    {
      symbol = '',
      chartId, // 兼容 OrderPage
      data,
      width = 800,
      height = 400,
      priceLines = [],
      markers = [],
      options, // 兼容 OrderPage
      onChartReady
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const managerRef = useRef<TradingViewChartManager | null>(null);

    // 使用 chartId 或 symbol 作为标识
    const chartSymbol = symbol || chartId || 'CHART';

    // 初始化图表
    useEffect(() => {
      if (!containerRef.current) return;

      try {
        const manager = new TradingViewChartManager();
        manager.initialize({
          symbol: chartSymbol,
          container: containerRef.current,
          width,
          height
        });

        managerRef.current = manager;

        // 设置数据
        if (data.length > 0) {
          manager.setData(data);
        }

        // 添加价格线
        priceLines.forEach((line) => {
          manager.addPriceLine(line);
        });

        // 回调
        if (onChartReady) {
          onChartReady(manager);
        }

        // 暴露给 ref
        if (ref) {
          if (typeof ref === 'function') {
            ref(manager);
          } else {
            ref.current = manager;
          }
        }

        return () => {
          manager.destroy();
          managerRef.current = null;
        };
      } catch (error) {
        console.error('Failed to initialize chart:', error);
      }
    }, [chartSymbol, width, height, onChartReady, ref]);

    // 更新数据
    useEffect(() => {
      if (managerRef.current && data.length > 0) {
        managerRef.current.setData(data);
      }
    }, [data]);

    // 更新价格线
    useEffect(() => {
      if (managerRef.current) {
        managerRef.current.clearPriceLines();
        priceLines.forEach((line) => {
          managerRef.current!.addPriceLine(line);
        });
      }
    }, [priceLines]);

    return (
      <div
        ref={containerRef}
        className="w-full rounded-lg overflow-hidden border border-white/5 bg-black/40"
        style={{ minHeight: height }}
      />
    );
  }
);

TradingViewChartComponent.displayName = 'TradingViewChartComponent';

// 默认导出（为了兼容默认导入）
export default TradingViewChartComponent;

