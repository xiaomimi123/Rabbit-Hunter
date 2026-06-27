import { ReactNode } from 'react';
import { cn, cardClassName } from './cn';

interface Props {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function Card({ title, subtitle, actions, children, className, bodyClassName }: Props) {
  return (
    <section className={cardClassName(className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {title && (
              <h3 className="text-sm font-semibold uppercase tracking-wider2 text-ivory">{title}</h3>
            )}
            {subtitle && <p className="mt-1 text-xs text-ivory-40">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn(bodyClassName)}>{children}</div>
    </section>
  );
}
