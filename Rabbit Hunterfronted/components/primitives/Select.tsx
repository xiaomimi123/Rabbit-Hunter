import React from 'react';

interface Option { value: string; label: string }
interface Props {
  value: string | null;
  options: Option[];
  onChange: (v: string) => void;
  className?: string;
  disabled?: boolean;
}

export function Select({ value, options, onChange, className = '', disabled }: Props) {
  return (
    <select
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className={`font-mono text-[0.85rem] bg-bg-base border border-hairline-strong px-3 py-1.5 text-ivory outline-none focus:border-brass ${className}`}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
