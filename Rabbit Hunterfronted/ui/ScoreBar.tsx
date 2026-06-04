import React from 'react';

interface ScoreBarProps {
  value: number;      // 0-100
  label?: string;
  showValue?: boolean;
  className?: string;
}

function barColor(v: number) {
  if (v >= 70) return 'bg-bull';
  if (v >= 45) return 'bg-primary';
  return 'bg-bear';
}

export function ScoreBar({ value, label, showValue = true, className = '' }: ScoreBarProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {label && <span className="text-text-muted text-xs w-20 truncate">{label}</span>}
      <div className="flex-1 h-1.5 bg-terminal-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor(clamped)}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showValue && (
        <span className="font-mono text-xs text-text-secondary w-8 text-right">
          {clamped.toFixed(0)}
        </span>
      )}
    </div>
  );
}

interface DimScoresProps {
  scores: { structure: number; volatility: number; sentiment: number; manipulation: number };
}

export function DimensionScores({ scores }: DimScoresProps) {
  return (
    <div className="space-y-1">
      <ScoreBar value={scores.structure}    label="结构" />
      <ScoreBar value={scores.volatility}   label="波动" />
      <ScoreBar value={scores.sentiment}    label="情绪" />
      <ScoreBar value={scores.manipulation} label="操控" />
    </div>
  );
}
