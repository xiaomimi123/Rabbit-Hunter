import React from 'react';
import { Tooltip } from '../primitives/Tooltip';
import { GLOSSARY } from '../../services/glossary';

interface Props {
  k: string;
  children?: React.ReactNode;
  className?: string;
}

export function Term({ k, children, className = '' }: Props) {
  const entry = GLOSSARY[k];
  if (!entry) {
    return <span className={className}>{children ?? k}</span>;
  }
  const content = (
    <div className="space-y-1">
      <div className="font-medium text-white">
        {entry.zh}
        {entry.en && <span className="ml-2 text-white/50 text-[10px] font-mono">{entry.en}</span>}
      </div>
      <div className="text-white/70">{entry.desc}</div>
      {entry.example && (
        <div className="text-cyan-300/70 text-[10px] border-t border-white/10 pt-1 mt-1 font-mono">
          ▶ {entry.example}
        </div>
      )}
    </div>
  );
  return (
    <Tooltip content={content} className={className}>
      <span className="cursor-help border-b border-dotted border-white/30 hover:border-cyan-400/70 hover:text-cyan-300 transition-colors">
        {children ?? k}
      </span>
    </Tooltip>
  );
}
