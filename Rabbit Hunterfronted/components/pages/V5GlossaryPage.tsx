import { useState } from 'react';
import { Search, BookOpen } from 'lucide-react';
import { GLOSSARY, GLOSSARY_CATEGORIES } from '../../services/glossary';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { cn, cardClassName } from '../primitives-v3/cn';

export function V5GlossaryPage() {
  const [filter, setFilter] = useState('');
  const entries = Object.values(GLOSSARY);
  const f = filter.trim().toLowerCase();
  const matchedCount = entries.filter(e =>
    !f || e.key.toLowerCase().includes(f) || e.zh.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f)
  ).length;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-6 space-y-6">
      <SectionTitle
        title="术语词典"
        subtitle="field manual · 系统术语 + 中文翻译 + 用例"
        action={
          <div className="flex items-center gap-2 rounded-2xl border border-hairline-strong bg-bg-base px-3 py-2">
            <Search className="h-4 w-4 text-ivory-40" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="搜索 SL / RSI / 胜率…"
              className="bg-transparent text-sm text-ivory outline-none placeholder:text-ivory-40 w-56"
            />
            <span className="text-xs text-ivory-40 whitespace-nowrap">
              {matchedCount} / {entries.length}
            </span>
          </div>
        }
      />

      <div className="space-y-6">
        {GLOSSARY_CATEGORIES.map(cat => {
          const items = entries.filter(e =>
            e.category === cat.name
            && (!f || e.key.toLowerCase().includes(f) || e.zh.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f))
          );
          if (items.length === 0) return null;
          return (
            <Card key={cat.name} title={cat.label} subtitle={`${items.length} terms`}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {items.map(e => (
                  <article key={e.key} className={cardClassName('!p-4 space-y-2 !rounded-2xl')}>
                    <div className="flex items-baseline gap-3 flex-wrap">
                      <span className="font-mono text-sm text-ink">{e.key}</span>
                      <span className="text-base text-ivory">{e.zh}</span>
                      {e.en && <span className="ml-auto text-xs text-ivory-40">{e.en}</span>}
                    </div>
                    <div className="text-sm text-ivory-70 leading-relaxed">{e.desc}</div>
                    {e.example && (
                      <div className="rounded-xl border-l-2 border-brass bg-brass/[0.06] px-3 py-1.5 font-mono text-xs text-ivory-70 leading-relaxed">
                        {e.example}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </Card>
          );
        })}
        {f && matchedCount === 0 && (
          <Card>
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-bg-elevated">
                <BookOpen className="h-5 w-5 text-ivory-40" />
              </div>
              <div className="text-sm text-ivory-70">
                未找到与 "<span className="text-ink">{filter}</span>" 匹配的术语
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
