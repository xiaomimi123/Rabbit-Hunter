import React, { useState } from 'react';
import { Card } from '../primitives/Card';
import { GLOSSARY, GLOSSARY_CATEGORIES } from '../../services/glossary';
import { Search } from 'lucide-react';

export function V5GlossaryPage() {
  const [filter, setFilter] = useState('');
  const entries = Object.values(GLOSSARY);
  const f = filter.trim().toLowerCase();

  return (
    <div className="space-y-4">
      <Card
        title="术语词典"
        actions={
          <div className="flex items-center gap-2">
            <Search size={14} className="text-white/40" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="搜索 SL / RSI / 胜率..."
              className="rounded-sm border border-white/10 bg-bg-base px-2 py-1 text-xs text-white outline-none focus:border-accent-info w-48"
            />
          </div>
        }
      >
        <div className="space-y-6">
          {GLOSSARY_CATEGORIES.map(cat => {
            const items = entries.filter(e =>
              e.category === cat.name
              && (!f || e.key.toLowerCase().includes(f) || e.zh.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f))
            );
            if (items.length === 0) return null;
            return (
              <div key={cat.name}>
                <div className="text-xs uppercase tracking-[0.2em] text-cyan-300/70 mb-2">▶ {cat.label}</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {items.map(e => (
                    <div key={e.key} className="rounded-md border border-white/10 bg-bg-base p-3">
                      <div className="flex items-baseline gap-2">
                        <span className="font-mono text-sm text-white">{e.key}</span>
                        <span className="text-sm text-white/80">{e.zh}</span>
                        {e.en && <span className="ml-auto text-[10px] font-mono text-white/40">{e.en}</span>}
                      </div>
                      <div className="mt-1 text-xs text-white/70">{e.desc}</div>
                      {e.example && (
                        <div className="mt-2 rounded-sm border-l-2 border-cyan-500/40 bg-cyan-500/5 px-2 py-1 text-[11px] text-cyan-200/80 font-mono">
                          {e.example}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
