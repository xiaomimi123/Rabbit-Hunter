import React from 'react';

interface Props {
  value: number;
  min?: number;
  max?: number;
  thresholds?: { warn?: number; danger?: number };
  label?: React.ReactNode;
  size?: number;
}

export function GaugeArc({ value, min = 0, max = 100, thresholds, label, size = 100 }: Props) {
  const v = Math.max(min, Math.min(max, value));
  const pct = (v - min) / (max - min);
  const angle = pct * 180 - 90;
  const radius = size / 2 - 8;
  const cx = size / 2;
  const cy = size / 2;
  const x = cx + radius * Math.cos(((angle - 90) * Math.PI) / 180);
  const y = cy + radius * Math.sin(((angle - 90) * Math.PI) / 180);

  let stroke = '#3B82F6';
  if (thresholds?.danger != null && v >= thresholds.danger) stroke = '#EF4444';
  else if (thresholds?.warn != null && v >= thresholds.warn) stroke = '#F59E0B';

  return (
    <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`}>
      <path
        d={`M ${8} ${cy} A ${radius} ${radius} 0 0 1 ${size - 8} ${cy}`}
        stroke="rgba(255,255,255,0.1)" strokeWidth={6} fill="none" strokeLinecap="round"
      />
      <path
        d={`M ${8} ${cy} A ${radius} ${radius} 0 0 ${pct > 0.5 ? 1 : 0} ${x} ${y}`}
        stroke={stroke} strokeWidth={6} fill="none" strokeLinecap="round"
      />
      <text x={cx} y={cy - 6} textAnchor="middle" fill="white" fontSize={size / 6} fontFamily="JetBrains Mono">
        {v.toFixed(1)}
      </text>
      {label && (
        <text x={cx} y={cy + 8} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={size / 12}>
          {label}
        </text>
      )}
    </svg>
  );
}
