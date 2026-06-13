import React from 'react';
import { NavLink } from 'react-router-dom';
import { useUIStore } from '../../services/store';
import {
  Activity, ListOrdered, Briefcase, BarChart3,
  Brain, History, SlidersHorizontal, Settings, Hand,
  ChevronLeft, ChevronRight, BookOpen,
} from 'lucide-react';

interface NavItem { to: string; label: string; Icon: any }

const GROUPS: { name: string; items: NavItem[] }[] = [
  { name: '交易', items: [
    { to: '/v5/signals', label: '实时信号', Icon: Activity },
    { to: '/v5/active', label: '活仓监控', Icon: Briefcase },
    { to: '/v5/orders', label: '订单历史', Icon: ListOrdered },
    { to: '/v5/manual', label: '手动开单', Icon: Hand },
  ]},
  { name: '智能', items: [
    { to: '/v5/ai', label: 'AI 状态', Icon: Brain },
    { to: '/v5/history', label: '信号历史', Icon: History },
    { to: '/v5/config', label: '策略配置', Icon: SlidersHorizontal },
  ]},
  { name: '系统', items: [
    { to: '/v5/dashboard', label: 'Dashboard', Icon: BarChart3 },
    { to: '/v5/settings', label: '系统设置', Icon: Settings },
    { to: '/v5/glossary', label: '术语词典', Icon: BookOpen },
  ]},
];

export function Sidebar() {
  const collapsed = useUIStore(s => s.sidebarCollapsed);
  const toggle = useUIStore(s => s.toggleSidebar);
  return (
    <aside className={`flex h-full flex-col border-r border-white/10 bg-bg-surface ${collapsed ? 'w-14' : 'w-52'} transition-all duration-base`}>
      <div className="flex h-12 items-center justify-between px-3 border-b border-white/10">
        {!collapsed && <span className="text-sm font-medium text-white">猎兔者 V5</span>}
        <button type="button" onClick={toggle} className="text-white/50 hover:text-white">
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto py-3 space-y-4">
        {GROUPS.map(g => (
          <div key={g.name}>
            {!collapsed && <div className="px-3 pb-1 text-[10px] uppercase tracking-wider text-white/40">{g.name}</div>}
            {g.items.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) => `flex items-center gap-2 px-3 py-1.5 text-sm ${
                  isActive ? 'bg-accent-info/15 text-accent-info' : 'text-white/70 hover:bg-white/5'
                }`}
              >
                <Icon size={16} />
                {!collapsed && <span>{label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
