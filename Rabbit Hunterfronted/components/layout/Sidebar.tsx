import { NavLink } from 'react-router-dom';
import {
  Activity, Briefcase, ListOrdered, Hand,
  Brain, History, SlidersHorizontal, BookText,
  LayoutDashboard, Settings, BookOpen, Bot,
} from 'lucide-react';
import { cn } from '../primitives-v3/cn';

interface NavItem { to: string; label: string; Icon: any }

const GROUPS: { name: string; items: NavItem[] }[] = [
  {
    name: '交易',
    items: [
      { to: '/v5/signals', label: '实时信号', Icon: Activity },
      { to: '/v5/active',  label: '活仓监控', Icon: Briefcase },
      { to: '/v5/orders',  label: '订单历史', Icon: ListOrdered },
      { to: '/v5/manual',  label: '手动开单', Icon: Hand },
    ],
  },
  {
    name: '智能',
    items: [
      { to: '/v5/ai',         label: 'AI 状态',    Icon: Brain },
      { to: '/v5/history',    label: '信号历史',   Icon: History },
      { to: '/v5/config',     label: '策略配置',   Icon: SlidersHorizontal },
      { to: '/v5/reflection', label: '复盘工作台', Icon: BookText },
    ],
  },
  {
    name: '系统',
    items: [
      { to: '/v5/dashboard', label: '仪表盘',    Icon: LayoutDashboard },
      { to: '/v5/settings',  label: '系统设置', Icon: Settings },
      { to: '/v5/glossary',  label: '术语词典', Icon: BookOpen },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="flex flex-col w-[240px] border-r border-zinc-800 bg-zinc-950/95 px-4 py-6 sticky top-0 h-screen overflow-y-auto">
      <div className="mb-8 flex items-center gap-3 px-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-500/15 text-indigo-300">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <div className="font-semibold text-zinc-50">猎兔者R</div>
          <div className="text-xs text-zinc-500">v6.0 · SHADOW</div>
        </div>
      </div>

      <nav className="flex-1 space-y-5">
        {GROUPS.map(g => (
          <div key={g.name}>
            <div className="px-3 pb-2 text-[10px] uppercase tracking-[0.18em] text-zinc-500">
              {g.name}
            </div>
            <div className="space-y-1">
              {g.items.map(({ to, label, Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      'flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-left text-sm transition',
                      isActive
                        ? 'bg-indigo-500/15 text-indigo-200'
                        : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100',
                    )
                  }
                >
                  <Icon className="h-4 w-4" />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
