import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Database, History,
  FlaskConical, Brain, Settings, Bot,
} from 'lucide-react';
import { cn } from '../primitives-v3/cn';

interface NavItem { to: string; label: string; Icon: any }

const NAV: NavItem[] = [
  { to: '/dashboard',  label: '仪表盘',   Icon: LayoutDashboard },
  { to: '/collect',    label: '采集数据', Icon: Database },
  { to: '/history',    label: '交易历史', Icon: History },
  { to: '/backtest',   label: '策略验证', Icon: FlaskConical },
  { to: '/learning',   label: 'AI 学习',  Icon: Brain },
  { to: '/settings',   label: '系统设置', Icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="flex flex-col w-[240px] border-r border-hairline bg-bg-base/95 px-4 py-6 sticky top-0 h-screen overflow-y-auto">
      <div className="mb-8 flex items-center gap-3 px-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-sm border border-brass/40 bg-brass-soft text-brass">
          <Bot className="h-5 w-5" />
        </div>
        <div>
          <div className="font-semibold text-ivory">猎兔者R</div>
          <div className="text-[10px] uppercase tracking-wider2 text-ivory-40 font-mono">v6.0 · SHADOW</div>
        </div>
      </div>

      <nav className="flex-1 space-y-1">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-left text-sm transition',
                isActive
                  ? 'border border-brass/40 bg-brass-soft text-brass'
                  : 'border border-transparent text-ivory-70 hover:bg-bg-elevated hover:text-ivory',
              )
            }
          >
            <Icon className="h-4 w-4" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-6 rounded-sm border border-hairline bg-bg-surface/60 p-3 text-xs">
        <div className="mb-1 font-medium uppercase tracking-wider2 text-[10px] text-ivory-40">深链入口</div>
        <div className="flex flex-col gap-1 text-ivory-70">
          <NavLink to="/portfolio" className="hover:text-brass">投资组合</NavLink>
          <NavLink to="/reliability" className="hover:text-brass">执行可靠性</NavLink>
          <NavLink to="/knowledge" className="hover:text-brass">知识层</NavLink>
          <NavLink to="/manual" className="hover:text-brass">手动开单</NavLink>
          <NavLink to="/glossary" className="hover:text-brass">术语词典</NavLink>
        </div>
      </div>
    </aside>
  );
}
