/**
 * Small visual primitives shared across the redesigned screens.
 *
 * Goal: stop sprinkling identical tailwind class strings into every component.
 * Every primitive here is a pure visual wrapper — no data fetching, no state.
 */

import React from 'react';

// ─── Card ──────────────────────────────────────────────────────────

interface CardProps {
  children: React.ReactNode;
  className?: string;
  inset?: boolean;
}

export const Card: React.FC<CardProps> = ({ children, className = '', inset }) => (
  <div
    className={
      'surface ' +
      (inset ? 'p-5 ' : '') +
      className
    }
  >
    {children}
  </div>
);

// ─── SectionHeader ─────────────────────────────────────────────────

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({ title, subtitle, right }) => (
  <div className="flex items-end justify-between mb-3">
    <div>
      <div className="text-[15px] font-medium text-text-primary tracking-tight">{title}</div>
      {subtitle && (
        <div className="text-[11px] text-text-muted mt-0.5">{subtitle}</div>
      )}
    </div>
    {right}
  </div>
);

// ─── StatTile ──────────────────────────────────────────────────────
// 财务数据 KPI 卡片 — 标签 + 大号 mono 数字 + 可选副标。

interface StatTileProps {
  label: string;
  value: string | React.ReactNode;
  hint?: string;
  trend?: 'up' | 'down' | 'flat';
  loading?: boolean;
}

export const StatTile: React.FC<StatTileProps> = ({ label, value, hint, trend, loading }) => {
  const trendClass =
    trend === 'up' ? 'text-bull' :
    trend === 'down' ? 'text-bear' :
    'text-text-primary';
  return (
    <div className="surface p-4">
      <div className="label-sm">{label}</div>
      <div className={`mt-2 text-2xl num font-medium ${trendClass} ${loading ? 'opacity-40' : ''}`}>
        {loading ? '—' : value}
      </div>
      {hint && (
        <div className="mt-1 text-[11px] text-text-muted">{hint}</div>
      )}
    </div>
  );
};

// ─── Pill (status / tag) ───────────────────────────────────────────

interface PillProps {
  children: React.ReactNode;
  tone?: 'neutral' | 'bull' | 'bear' | 'accent' | 'warn';
  size?: 'sm' | 'md';
}

export const Pill: React.FC<PillProps> = ({ children, tone = 'neutral', size = 'sm' }) => {
  const tones = {
    neutral: 'bg-white/[0.04] text-text-secondary border-white/10',
    bull:    'bg-bull-dim text-bull border-bull/25',
    bear:    'bg-bear-dim text-bear border-bear/25',
    accent:  'bg-primary-dim text-primary border-primary/25',
    warn:    'bg-warn/10 text-warn border-warn/25',
  };
  const sizing = size === 'sm'
    ? 'px-1.5 py-0.5 text-[10px]'
    : 'px-2 py-1 text-xs';
  return (
    <span className={`inline-flex items-center gap-1 rounded border ${sizing} ${tones[tone]} uppercase tracking-micro font-medium`}>
      {children}
    </span>
  );
};

// ─── NumberCell — financial number that signs/colors itself ────────

interface NumberCellProps {
  value: number | null | undefined;
  decimals?: number;
  suffix?: string;
  signColor?: boolean;
  className?: string;
}

export const NumberCell: React.FC<NumberCellProps> = ({
  value, decimals = 2, suffix = '', signColor = false, className = '',
}) => {
  if (value == null || Number.isNaN(value)) {
    return <span className={`num text-text-muted ${className}`}>—</span>;
  }
  const tone =
    !signColor ? '' :
    value > 0 ? 'text-bull' :
    value < 0 ? 'text-bear' :
    'text-text-secondary';
  const sign = signColor && value > 0 ? '+' : '';
  return (
    <span className={`num ${tone} ${className}`}>
      {sign}{value.toFixed(decimals)}{suffix}
    </span>
  );
};

// ─── EmptyState ────────────────────────────────────────────────────

interface EmptyStateProps {
  title: string;
  hint?: string;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ title, hint, icon }) => (
  <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
    {icon && (
      <div className="text-text-muted mb-3">{icon}</div>
    )}
    <div className="text-sm text-text-secondary">{title}</div>
    {hint && (
      <div className="text-[11px] text-text-muted mt-1 max-w-xs">{hint}</div>
    )}
  </div>
);
