import { ReactNode } from 'react';
import { Aperture } from './Aperture';

interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
  /** Show an Aperture marker before the title. Default true when title is set. */
  aperture?: boolean;
}

export function Card({ title, actions, className = '', children, aperture }: CardProps) {
  const showAperture = aperture ?? !!title;
  return (
    <section className={`bg-bg-base ${className}`}>
      {(title || actions) && (
        <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
          {showAperture && title && <Aperture size={18} className="text-brass" />}
          {title && <h3 className="font-display text-[1.4rem] tracking-tight leading-none">{title}</h3>}
          {actions && (
            <div className="ml-auto flex items-center gap-2 font-mono text-[0.7rem] text-ivory-40 tracking-wide">
              {actions}
            </div>
          )}
        </header>
      )}
      {children}
    </section>
  );
}
