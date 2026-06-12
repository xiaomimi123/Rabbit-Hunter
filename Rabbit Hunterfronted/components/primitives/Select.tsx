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
      className={`rounded-sm border border-white/10 bg-bg-base px-2 py-1 text-sm text-white outline-none focus:border-accent-info ${className}`}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
