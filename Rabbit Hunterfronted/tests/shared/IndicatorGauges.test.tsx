import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { IndicatorGauges } from '@/components/shared/IndicatorGauges';

describe('IndicatorGauges', () => {
  it('renders RSI value and tone label when overbought', () => {
    render(<IndicatorGauges
      rsi_15m={72.1} rsi_4h={68} macd_hist_15m={-0.0012}
      macd_hist_prev_15m={0.0008} atr_15m={0.0015} />);
    expect(screen.getByText(/72\.1/)).toBeInTheDocument();
    expect(screen.getByText(/超买/)).toBeInTheDocument();
  });

  it('shows oversold tone when RSI < 30', () => {
    render(<IndicatorGauges
      rsi_15m={22.5} rsi_4h={32} macd_hist_15m={0.0005}
      macd_hist_prev_15m={-0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/超卖/)).toBeInTheDocument();
  });

  it('flags MACD bullish cross when hist flips negative→positive', () => {
    render(<IndicatorGauges
      rsi_15m={45} rsi_4h={50} macd_hist_15m={0.0005}
      macd_hist_prev_15m={-0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/金叉/)).toBeInTheDocument();
  });

  it('flags MACD bearish cross when hist flips positive→negative', () => {
    render(<IndicatorGauges
      rsi_15m={70} rsi_4h={50} macd_hist_15m={-0.0005}
      macd_hist_prev_15m={0.0004} atr_15m={0.001} />);
    expect(screen.getByText(/死叉/)).toBeInTheDocument();
  });
});
