import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Briefcase, LineChart, History,
  FlaskConical, Shield, Eye, Stethoscope, Settings, Bot, BookOpen,
} from 'lucide-react';
import { cn } from '../primitives-v3/cn';

interface NavItem { to: string; label: string; Icon: any }

const NAV: NavItem[] = [
  { to: '/dashboard',   label: '仪表盘',     Icon: LayoutDashboard },
  { to: '/portfolio',   label: '投资组合',   Icon: Briefcase },
  { to: '/market',      label: '市场分析',   Icon: LineChart },
  { to: '/history',     label: '交易历史',   Icon: History },
  { to: '/backtest',    label: '策略验证',   Icon: FlaskConical },
  { to: '/reliability', label: '执行可靠性', Icon: Shield },
  { to: '/audit',       label: '监控审计',   Icon: Eye },
  { to: '/diagnostics', label: '策略诊断',   Icon: Stethoscope },
  { to: '/knowledge',   label: '知识层',     Icon: BookOpen },
  { to: '/settings',    label: '系统设置',   Icon: Settings },
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

      <nav className="flex-1 space-y-1">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm transition',
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
      </nav>

      <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/60 p-3 text-xs text-zinc-500">
        <div className="mb-1 font-medium text-zinc-300">深链入口</div>
        <div className="flex flex-col gap-1 text-zinc-400">
          <NavLink to="/manual" className="hover:text-indigo-300">手动开单</NavLink>
          <NavLink to="/glossary" className="hover:text-indigo-300">术语词典</NavLink>
        </div>
      </div>
    </aside>
  );
}
