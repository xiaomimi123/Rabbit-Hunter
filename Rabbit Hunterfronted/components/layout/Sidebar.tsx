import { NavLink } from 'react-router-dom';
import {
  LayoutGrid, TrendingUp, Brain, Settings,
  PieChart, History, FlaskConical, BookOpen,
} from 'lucide-react';
import { cn } from '../primitives-v3/cn';
import { ModeIndicator } from './ModeIndicator';

interface NavItem { to: string; label: string; Icon: any }

// V3 — 8 项主导航 (4 主流程 + 4 数据/分析,2026-06-27)
const NAV: NavItem[] = [
  { to: '/overview',  label: '总览',     Icon: LayoutGrid },
  { to: '/market',    label: '市场数据', Icon: TrendingUp },
  { to: '/learning',  label: 'AI 学习',  Icon: Brain },
  { to: '/portfolio', label: '投资组合', Icon: PieChart },
  { to: '/history',   label: '交易历史', Icon: History },
  { to: '/backtest',  label: '回测验证', Icon: FlaskConical },
  { to: '/knowledge', label: '知识层',   Icon: BookOpen },
  { to: '/settings',  label: '设置',     Icon: Settings },
];

// 深链 — 低频辅助页面 (中控仪表/手动开单 2026-06-28 用户要求移除入口,route 仍保留)
const DEEP_LINKS = [
  { to: '/audit',       label: '反思审计' },
  { to: '/diagnostics', label: 'AI 诊断' },
  { to: '/reliability', label: '执行可靠性' },
  { to: '/collect',     label: '数据采集' },
  { to: '/glossary',    label: '术语词典' },
];

export function Sidebar() {
  return (
    <aside className="flex flex-col w-[212px] shrink-0 border-r border-line-soft bg-[#0C1117] px-3 py-[18px] sticky top-0 h-screen overflow-y-auto">
      {/* Brand */}
      <div className="mb-1.5 flex items-center gap-2.5 px-2 pb-[18px]">
        <div className="flex h-7 w-7 items-center justify-center rounded-[7px] border-[1.5px] border-amber text-amber font-bold text-[15px]">
          兔
        </div>
        <div>
          <div className="font-semibold text-[15px] tracking-[0.01em] text-v3text">Rabbit Hunter</div>
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-v3faint">私人中控</div>
        </div>
      </div>

      {/* Main nav — 4 主流程 */}
      <nav className="mt-1.5 flex flex-col gap-[3px]">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-[11px] px-[11px] py-2.5 rounded-lg text-[13.5px] font-medium transition',
                isActive
                  ? 'bg-[#19222D] text-v3text shadow-[inset_2px_0_0_var(--tw-shadow-color)] shadow-amber'
                  : 'text-v3muted hover:bg-[#141B23] hover:text-v3text',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={cn('h-[17px] w-[17px] shrink-0', isActive ? 'text-amber opacity-100' : 'opacity-85')} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* 深链区 */}
      <details className="mt-4 group">
        <summary className="cursor-pointer list-none px-[11px] py-2 text-[10px] uppercase tracking-[0.08em] text-v3faint hover:text-v3muted transition select-none">
          深链 ▾
        </summary>
        <div className="mt-1 flex flex-col gap-0.5">
          {DEEP_LINKS.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  'px-[14px] py-1.5 text-[12px] transition',
                  isActive
                    ? 'text-amber'
                    : 'text-v3muted hover:text-v3text',
                )
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      </details>

      {/* 底部签名: 模式指示器 */}
      <div className="mt-auto pt-2.5 px-1">
        <ModeIndicator />
      </div>
    </aside>
  );
}
