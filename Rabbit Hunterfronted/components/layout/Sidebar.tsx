import { NavLink } from 'react-router-dom';
import { Aperture } from '../primitives/Aperture';

interface NavItem { to: string; label: string; glyph: string; }

const GROUPS: { name: string; items: NavItem[] }[] = [
  {
    name: '交易',
    items: [
      { to: '/v5/signals', label: '实时信号', glyph: '●' },
      { to: '/v5/active',  label: '活仓监控', glyph: '●' },
      { to: '/v5/orders',  label: '订单历史', glyph: '●' },
      { to: '/v5/manual',  label: '手动开单', glyph: '●' },
    ],
  },
  {
    name: '智能',
    items: [
      { to: '/v5/ai',         label: 'AI 状态',    glyph: '◆' },
      { to: '/v5/history',    label: '信号历史',   glyph: '◆' },
      { to: '/v5/config',     label: '策略配置',   glyph: '◆' },
      { to: '/v5/reflection', label: '复盘工作台', glyph: '◆' },
    ],
  },
  {
    name: '系统',
    items: [
      { to: '/v5/dashboard', label: 'Dashboard', glyph: '⊕' },
      { to: '/v5/settings',  label: '系统设置',  glyph: '○' },
      { to: '/v5/glossary',  label: '术语词典',  glyph: '○' },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="flex flex-col w-[232px] border-r border-hairline bg-bg-base py-5 sticky top-0 h-screen overflow-y-auto">
      <div className="flex items-center gap-3 px-5 pb-6 border-b border-hairline">
        <Aperture size={28} className="text-brass" />
        <div>
          <div className="font-display text-[1.4rem] leading-none">
            猎兔者<span className="not-italic text-brass">·</span>R
          </div>
          <div className="font-mono text-[0.65rem] text-ivory-40 tracking-wider2 mt-1">
            v6.0 · FIELD
          </div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto pt-[18px] pb-2">
        {GROUPS.map(g => (
          <div key={g.name} className="pb-1.5">
            <div className="px-5 pb-2 font-mono text-[0.62rem] tracking-wider4 text-ivory-40 uppercase">
              {g.name}
            </div>
            {g.items.map(({ to, label, glyph }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 py-1.5 px-5 font-cn text-sm border-l-2 transition-all duration-200 ${
                    isActive
                      ? 'text-brass border-brass bg-brass-soft'
                      : 'text-ivory-70 border-transparent hover:text-ivory hover:bg-white/[0.02]'
                  }`
                }
              >
                <span className="font-mono text-[0.7rem] w-4 opacity-60">{glyph}</span>
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
