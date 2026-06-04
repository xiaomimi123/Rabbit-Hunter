/**
 * TradingView Lightweight Charts 服务
 * K 线图表管理和配置
 */

import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
  CandlestickData
} from 'lightweight-charts';

interface ChartConfig {
  symbol: string;
  container: HTMLDivElement;
  width: number;
  height: number;
  theme?: 'dark' | 'light';
}

interface PriceLine {
  price: number;
  color?: string;
  width?: number;
  title?: string;
}

// ============== 赛博朋克主题配置 ==============

const CYBERPUNK_DARK_THEME = {
  layout: {
    background: { type: ColorType.Solid, color: '#050505' },
    textColor: '#d1d5db',
    fontFamily: 'JetBrains Mono, monospace'
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: false,
    barSpacing: 12
  },
  rightPriceScale: {
    autoScale: true,
    textColor: '#7B61FF',
    borderColor: '#ffffff10'
  },
  grid: {
    vertLines: { color: '#ffffff05', visible: true },
    horzLines: { color: '#ffffff05', visible: true }
  },
  crosshair: {
    mode: 1,
    vertLine: {
      color: '#7B61FF80',
      width: 1,
      style: 1,
      visible: true,
      labelVisible: true,
      labelBackgroundColor: '#7B61FF'
    },
    horzLine: {
      color: '#7B61FF80',
      width: 1,
      style: 1,
      visible: true,
      labelVisible: true,
      labelBackgroundColor: '#7B61FF'
    }
  }
};

// ============== TradingViewChartManager ==============

export class TradingViewChartManager {
  private chart: IChartApi | null = null;
  private candlestickSeries: ISeriesApi<'Candlestick'> | null = null;
  private priceLines: Map<string, any> = new Map();

  /**
   * 初始化图表
   */
  initialize(config: ChartConfig): void {
    try {
      this.chart = createChart(config.container, {
        ...CYBERPUNK_DARK_THEME,
        width: config.width,
        height: config.height
      } as any);

      // 添加蜡烛图系列
      this.candlestickSeries = this.chart.addCandlestickSeries({
        upColor: '#00FF9D',
        downColor: '#FF2E2E',
        borderUpColor: '#00FF9D',
        borderDownColor: '#FF2E2E',
        wickUpColor: '#00FF9D',
        wickDownColor: '#FF2E2E'
      });

      console.log(`[Chart] Initialized for ${config.symbol}`);
    } catch (error) {
      console.error('[Chart] Initialization failed:', error);
      throw error;
    }
  }

  /**
   * 设置完整数据
   */
  setData(data: CandlestickData[]): void {
    if (!this.candlestickSeries) {
      console.warn('[Chart] Series not initialized');
      return;
    }

    try {
      this.candlestickSeries.setData(data);
      this.chart?.timeScale().fitContent();
      console.log(`[Chart] Data set: ${data.length} candles`);
    } catch (error) {
      console.error('[Chart] Failed to set data:', error);
    }
  }

  /**
   * 更新最后一根蜡烛 (实时)
   */
  updateLatestCandle(candle: CandlestickData): void {
    if (!this.candlestickSeries) {
      console.warn('[Chart] Series not initialized');
      return;
    }

    try {
      this.candlestickSeries.update(candle);
    } catch (error) {
      console.error('[Chart] Failed to update candle:', error);
    }
  }

  /**
   * 添加价格线 (支撑/阻力/止损/TP)
   */
  addPriceLine(priceLine: PriceLine): string {
    if (!this.candlestickSeries) {
      console.warn('[Chart] Series not initialized');
      return '';
    }

    try {
      const lineId = `line_${Date.now()}_${Math.random()}`;

      this.candlestickSeries.createPriceLine({
        price: priceLine.price,
        color: priceLine.color || '#7B61FF',
        lineWidth: priceLine.width || 1,
        lineStyle: 0, // 0: solid, 1: dotted, 2: dashed
        axisLabelVisible: true,
        title: priceLine.title || `${priceLine.price.toFixed(2)}`
      });

      this.priceLines.set(lineId, priceLine);
      return lineId;
    } catch (error) {
      console.error('[Chart] Failed to add price line:', error);
      return '';
    }
  }

  /**
   * 移除价格线
   */
  removePriceLine(lineId: string): void {
    this.priceLines.delete(lineId);
    // Note: lightweight-charts 目前不提供直接移除 price line 的 API
    // 需要重新创建所有 price lines
  }

  /**
   * 清空所有价格线
   */
  clearPriceLines(): void {
    this.priceLines.clear();
  }

  /**
   * 响应式调整大小
   */
  applyOptions(options: any): void {
    if (this.chart) {
      this.chart.applyOptions(options);
    }
  }

  /**
   * 订阅点击事件
   */
  subscribeClick(callback: (param: any) => void): void {
    if (this.chart) {
      this.chart.subscribeClick(callback);
    }
  }

  /**
   * 订阅鼠标移动事件
   */
  subscribeCrosshairMove(callback: (param: any) => void): void {
    if (this.chart) {
      this.chart.subscribeCrosshairMove(callback);
    }
  }

  /**
   * 销毁图表
   */
  destroy(): void {
    try {
      if (this.chart) {
        this.chart.remove();
      }
      this.chart = null;
      this.candlestickSeries = null;
      this.priceLines.clear();
      console.log('[Chart] Destroyed');
    } catch (error) {
      console.error('[Chart] Destruction failed:', error);
    }
  }

  /**
   * 获取图表实例 (高级用法)
   */
  getChart(): IChartApi | null {
    return this.chart;
  }

  /**
   * 获取系列实例
   */
  getSeries(): ISeriesApi<'Candlestick'> | null {
    return this.candlestickSeries;
  }
}

