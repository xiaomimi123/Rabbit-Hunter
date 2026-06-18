import { ReactNode } from 'react';
import { Tooltip } from '../primitives/Tooltip';
import { GLOSSARY } from '../../services/glossary';

interface Props {
  k: string;
  children?: ReactNode;
  className?: string;
}

export function Term({ k, children, className = '' }: Props) {
  const entry = GLOSSARY[k];
  if (!entry) {
    return <span className={className}>{children ?? k}</span>;
  }
  const content = (
    <div className="flex flex-col gap-1">
      <div className="font-display text-[1rem] text-ivory">
        {entry.zh}
        {entry.en && <span className="ml-2 text-ivory-40 text-[0.7rem] font-mono">{entry.en}</span>}
      </div>
      <div className="text-ivory-70 font-body italic">{entry.desc}</div>
      {entry.example && (
        <div className="text-brass text-[0.7rem] border-t border-hairline pt-1 mt-1 font-mono not-italic">
          <span className="mr-1">▶</span>{entry.example}
        </div>
      )}
    </div>
  );
  return (
    <Tooltip content={content} className={className}>
      <span className="cursor-help border-b border-dotted border-ivory-25 hover:border-brass hover:text-brass transition-colors">
        {children ?? k}
      </span>
    </Tooltip>
  );
}
