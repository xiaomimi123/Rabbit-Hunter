interface Props {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  className?: string;
}

export function Slider({ value, min, max, step = 1, onChange, className = '' }: Props) {
  return (
    <input
      type="range"
      value={value}
      min={min}
      max={max}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className={`h-1.5 w-full appearance-none bg-white/[0.06] outline-none accent-brass ${className}`}
    />
  );
}
