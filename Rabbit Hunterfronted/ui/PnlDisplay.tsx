import React from 'react';

interface PnlDisplayProps {
  value: number;       // absolute PnL in quote currency
  percent?: number;    // optional % value
  className?: string;
}

export function PnlDisplay({ value, percent, className = '' }: PnlDisplayProps) {
  const isPositive = value >= 0;
  const color = isPositive ? 'text-bull' : 'text-bear';
  const sign = isPositive ? '+' : '';

  return (
    <span className={`font-mono tabular-nums ${color} ${className}`}>
      {sign}{value.toFixed(2)}
      {percent !== undefined && (
        <span className="text-text-secondary ml-1 text-xs">
          ({sign}{percent.toFixed(2)}%)
        </span>
      )}
    </span>
  );
}
