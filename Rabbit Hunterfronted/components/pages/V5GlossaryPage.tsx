import { useState } from 'react';
import { GLOSSARY, GLOSSARY_CATEGORIES } from '../../services/glossary';
import { Aperture } from '../primitives/Aperture';
import { Search } from 'lucide-react';

export function V5GlossaryPage() {
  const [filter, setFilter] = useState('');
  const entries = Object.values(GLOSSARY);
  const f = filter.trim().toLowerCase();
  const matchedCount = entries.filter(e =>
    !f || e.key.toLowerCase().includes(f) || e.zh.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f)
  ).length;

  return (
    <div className="px-8 py-7 pb-16 flex flex-col gap-7 max-w-[1400px]">
      <header className="grid grid-cols-[1fr_auto] items-end gap-6 pb-4 border-b border-hairline-strong">
        <div className="flex items-center gap-4">
          <Aperture size={34} rotate className="text-brass" />
          <div>
            <h1 className="font-display text-[2.6rem] leading-none tracking-tight">术语词典</h1>
            <p className="font-cn text-ivory-40 text-[0.85rem] mt-1.5">术语词典 · field manual</p>
          </div>
        </div>
        <div className="flex items-center gap-3 border border-hairline-strong px-3 py-2 bg-bg-base">
          <Search size={14} className="text-ivory-40" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索 SL / RSI / 胜率..."
            className="font-mono text-[0.85rem] bg-transparent text-ivory outline-none w-56 placeholder:text-ivory-40 placeholder:italic"
          />
          <span className="font-mono text-[0.7rem] text-ivory-40 tracking-wide">
            {matchedCount} / {entries.length}
          </span>
        </div>
      </header>

      <div className="flex flex-col gap-7">
        {GLOSSARY_CATEGORIES.map(cat => {
          const items = entries.filter(e =>
            e.category === cat.name
            && (!f || e.key.toLowerCase().includes(f) || e.zh.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f))
          );
          if (items.length === 0) return null;
          return (
            <section key={cat.name} className="grid grid-cols-[1fr_200px] gap-7 items-start max-[1100px]:grid-cols-1">
              <div>
                <header className="flex items-center gap-3.5 pb-4 border-b border-hairline mb-5">
                  <Aperture size={18} className="text-brass" />
                  <h2 className="font-display text-[1.4rem] tracking-tight leading-none">{cat.label}</h2>
                  <span className="ml-auto font-mono text-[0.7rem] text-ivory-40 tracking-wide">{items.length} terms</span>
                </header>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-hairline border border-hairline">
                  {items.map(e => (
                    <article key={e.key} className="bg-bg-base p-4 flex flex-col gap-2">
                      <div className="flex items-baseline gap-3">
                        <span className="font-mono text-[0.85rem] text-brass tracking-wide">{e.key}</span>
                        <span className="font-display text-[1rem] text-ivory">{e.zh}</span>
                        {e.en && <span className="ml-auto font-mono text-[0.7rem] text-ivory-40">{e.en}</span>}
                      </div>
                      <div className="font-body text-[0.85rem] text-ivory-70 leading-relaxed">{e.desc}</div>
                      {e.example && (
                        <div className="font-mono text-[0.78rem] text-ivory-70 border-l-2 border-brass bg-brass-soft px-3 py-1.5 leading-relaxed">
                          <span className="text-brass mr-1.5">▌</span>{e.example}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              </div>
              <aside className="font-body italic text-[0.78rem] text-ivory-40 leading-snug pt-[50px] border-l border-hairline pl-4 max-[1100px]:hidden">
                {/* future category-level annotation */}
              </aside>
            </section>
          );
        })}
        {f && matchedCount === 0 && (
          <div className="py-14 text-center font-body italic text-ivory-40">
            <Aperture size={42} rotate="slow" className="text-ivory-25 mx-auto block mb-3" />
            <span className="opacity-60 mr-2">▌</span>未找到与 "<span className="text-brass not-italic">{filter}</span>" 匹配的术语
          </div>
        )}
      </div>
    </div>
  );
}
