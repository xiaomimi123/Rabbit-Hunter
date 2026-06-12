import React, { useState, useEffect } from 'react';

interface Props {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}

export function NumberInput({ value, min, max, step = 0.01, onChange, className = '' }: Props) {
  const [draft, setDraft] = useState(String(value));

  // Sync draft when value changes from outside (only when not equal to parsed draft)
  useEffect(() => {
    const parsed = parseFloat(draft);
    if (isNaN(parsed) || parsed !== value) {
      setDraft(String(value));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    setDraft(raw);
    const n = Number(raw);
    if (raw === '' || Number.isNaN(n)) return;
    const clamped = Math.max(min ?? -Infinity, Math.min(max ?? Infinity, n));
    onChange(clamped);
  };

  const handleBlur = () => {
    const n = Number(draft);
    if (draft === '' || Number.isNaN(n)) {
      setDraft(String(value));
      return;
    }
    const clamped = Math.max(min ?? -Infinity, Math.min(max ?? Infinity, n));
    setDraft(String(clamped));
    onChange(clamped);
  };

  return (
    <input
      type="number"
      value={draft}
      min={min}
      max={max}
      step={step}
      onChange={handleChange}
      onBlur={handleBlur}
      className={`w-24 rounded-sm border border-white/10 bg-bg-base px-2 py-1 text-right font-mono text-sm text-white outline-none focus:border-accent-info ${className}`}
    />
  );
}
