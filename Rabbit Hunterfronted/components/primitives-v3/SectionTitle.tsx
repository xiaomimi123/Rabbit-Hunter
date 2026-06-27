import { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function SectionTitle({ title, subtitle, action }: Props) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold text-ivory">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-ivory-70">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
