import React from 'react';

type Variant = 'bull' | 'bear' | 'warn' | 'primary' | 'muted' | 'safe' | 'danger';

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}

const variantClass: Record<Variant, string> = {
  bull:    'bg-bull-dim text-bull border border-bull/30',
  bear:    'bg-bear-dim text-bear border border-bear/30',
  warn:    'bg-warn/10 text-warn border border-warn/30',
  primary: 'bg-primary-dim text-primary border border-primary/30',
  muted:   'bg-terminal-border text-text-muted border border-terminal-border',
  safe:    'bg-bull-dim text-bull border border-bull/30',
  danger:  'bg-bear-dim text-bear border border-bear/30',
};

export function Badge({ variant = 'muted', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase tracking-wide ${variantClass[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Convenience helpers */
export function RiskBadge({ label }: { label: 'BLOCK' | 'WATCH' | 'TRADE' }) {
  const map = { BLOCK: 'danger', WATCH: 'warn', TRADE: 'bull' } as const;
  return <Badge variant={map[label]}>{label}</Badge>;
}

export function SideBadge({ side }: { side: 'LONG' | 'SHORT' | 'NONE' }) {
  const map = { LONG: 'bull', SHORT: 'bear', NONE: 'muted' } as const;
  return <Badge variant={map[side]}>{side}</Badge>;
}
