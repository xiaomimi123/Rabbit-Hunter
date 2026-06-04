/**
 * Layout v5.0 — 左侧边栏 + 顶栏 + 内容区
 *
 * 结构：
 *   ┌──────────────────────────────────────────┐
 *   │  顶栏 48px (Logo + 策略状态 + 系统指示)   │
 *   ├────────┬─────────────────────────────────┤
 *   │ 侧边栏 │          内容区                  │
 *   │ 220px  │          overflow-y-auto         │
 *   │ (可折  │                                  │
 *   │  叠至  │                                  │
 *   │  64px) │                                  │
 *   └────────┴─────────────────────────────────┘
 */

import React, { useState } from 'react';
import {
  Target, Briefcase, Crosshair, BrainCircuit, Zap, Activity,
  BarChart3, Settings, LayoutDashboard, ChevronLeft, ChevronRight,
  Skull, Circle,
} from 'lucide-react';
import { ViewType } from '../types';
import { SystemState } from '../types';
import { useSystemStatus } from '../hooks/useSystemStatus';

// ─── nav config ──────────────────────────────────────────────────────────────

interface NavItem {
  id: ViewType;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: '交易',
    items: [
      { id: 'KILL_BOARD',  label: 'Kill Board',  icon: Target },
      { id: 'POSITIONS',   label: '持仓管理',    icon: Briefcase },
      { id: 'ORDER',       label: '手动下单',    icon: Crosshair },
    ],
  },
  {
    label: 'AI 系统',
    items: [
      { id: 'AI_STATUS',      label: 'AI 状态',  icon: BrainCircuit },
      { id: 'WEIGHT_HISTORY', label: 'AI 权重',  icon: Activity },
      { id: 'TRADE_SCORES',   label: '交易评分', icon: BarChart3 },
      { id: 'STRATEGY_CONFIG',label: '策略配置', icon: Zap },
    ],
  },
  {
    label: '系统',
    items: [
      { id: 'DASHBOARD', label: '仪表盘',  icon: LayoutDashboard },
      { id: 'SETTINGS',  label: '系统设置', icon: Settings },
    ],
  },
];

// ─── top bar ─────────────────────────────────────────────────────────────────

interface TopBarProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  systemMode: SystemState;
  onToggleMode: () => void;
}

const TopBar: React.FC<TopBarProps> = ({ sidebarCollapsed, onToggleSidebar, systemMode, onToggleMode }) => (
  <header className="h-12 flex items-center justify-between px-4 bg-terminal-card border-b border-terminal-border shrink-0 z-20">
    {/* Left: toggle + logo */}
    <div className="flex items-center gap-3">
      <button
        onClick={onToggleSidebar}
        className="p-1.5 rounded text-text-muted hover:text-text-primary hover:bg-terminal-hover transition-colors"
      >
        {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded bg-primary/20 border border-primary/40 flex items-center justify-center">
          <Skull size={13} className="text-primary" />
        </div>
        <div className="leading-none">
          <div className="text-[11px] font-bold text-text-primary tracking-widest uppercase font-mono">
            Rabbit Hunter
          </div>
          <div className="text-[9px] text-text-muted font-mono">v5.0</div>
        </div>
      </div>
    </div>

    {/* Center: strategy badges */}
    <div className="flex items-center gap-2">
      <StrategyBadge color="bull"  icon={Crosshair} label="SNIPER"  />
      <StrategyBadge color="bear"  icon={Skull}     label="VULTURE" />
    </div>

    {/* Right: mode toggle + status */}
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-1.5 text-[10px] font-mono">
        <span className={systemMode === SystemState.SHADOW ? 'text-warn' : 'text-text-muted'}>
          影子
        </span>
        <button
          onClick={onToggleMode}
          className={`relative w-9 h-5 rounded-full transition-colors duration-300 border ${
            systemMode === SystemState.LIVE
              ? 'bg-bear/20 border-bear/40'
              : 'bg-warn/10 border-warn/30'
          }`}
        >
          <div className={`absolute top-0.5 w-4 h-4 rounded-full transition-all duration-300 ${
            systemMode === SystemState.LIVE
              ? 'left-[18px] bg-bear shadow-[0_0_6px_#f6465d]'
              : 'left-0.5 bg-warn shadow-[0_0_6px_#f59e0b]'
          }`} />
        </button>
        <span className={systemMode === SystemState.LIVE ? 'text-bear font-bold' : 'text-text-muted'}>
          实盘
        </span>
      </div>
    </div>
  </header>
);

// ─── strategy badge ───────────────────────────────────────────────────────────

const BADGE_COLORS = {
  bull:    { bg: 'bg-bull/10',    border: 'border-bull/30',    text: 'text-bull' },
  bear:    { bg: 'bg-bear/10',    border: 'border-bear/30',    text: 'text-bear' },
  primary: { bg: 'bg-primary/10', border: 'border-primary/30', text: 'text-primary' },
  muted:   { bg: 'bg-white/5',    border: 'border-white/10',   text: 'text-text-muted' },
};

interface StrategyBadgeProps {
  color: keyof typeof BADGE_COLORS;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  dim?: boolean;
}

const StrategyBadge: React.FC<StrategyBadgeProps> = ({ color, icon: Icon, label, dim }) => {
  const c = BADGE_COLORS[color];
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded ${c.bg} border ${c.border} ${dim ? 'opacity-40' : ''}`}>
      <Icon size={11} className={c.text} />
      <span className={`text-[10px] font-mono font-bold ${c.text}`}>{label}</span>
    </div>
  );
};

// ─── sidebar ─────────────────────────────────────────────────────────────────

interface SidebarProps {
  collapsed: boolean;
  activeView: ViewType;
  onViewChange: (v: ViewType) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, activeView, onViewChange }) => {
  const { data: sysStatus } = useSystemStatus();
  const collectorRunning = sysStatus?.collector_running ?? false;
  const apiOnline = sysStatus?.api_online ?? true;

  return (
    <aside
      className={`flex flex-col bg-terminal-card border-r border-terminal-border transition-all duration-300 shrink-0 ${
        collapsed ? 'w-16' : 'w-[220px]'
      }`}
    >
      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {/* Group label — hide when collapsed */}
            {!collapsed && (
              <div className="px-2 mb-1.5 text-[9px] font-mono font-bold text-text-muted uppercase tracking-widest">
                {group.label}
              </div>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = activeView === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onViewChange(item.id)}
                    title={collapsed ? item.label : undefined}
                    className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-lg transition-all duration-150 group ${
                      active
                        ? 'bg-primary/15 text-primary border border-primary/25'
                        : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary border border-transparent'
                    }`}
                  >
                    <item.icon
                      size={16}
                      className={`shrink-0 ${active ? 'text-primary' : 'text-text-muted group-hover:text-text-secondary'}`}
                    />
                    {!collapsed && (
                      <span className="text-xs font-mono truncate">{item.label}</span>
                    )}
                    {active && !collapsed && (
                      <div className="ml-auto w-1 h-1 rounded-full bg-primary" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Bottom: system status */}
      <div className={`border-t border-terminal-border px-3 py-3 space-y-2 ${collapsed ? 'flex flex-col items-center' : ''}`}>
        {collapsed ? (
          <>
            <StatusDot ok={collectorRunning} title="采集器" />
            <StatusDot ok={apiOnline} title="API" />
          </>
        ) : (
          <>
            <StatusRow label="采集器" ok={collectorRunning} />
            <StatusRow label="API 服务" ok={apiOnline} />
          </>
        )}
      </div>
    </aside>
  );
};

// ─── status helpers ───────────────────────────────────────────────────────────

const StatusRow: React.FC<{ label: string; ok: boolean }> = ({ label, ok }) => (
  <div className="flex items-center justify-between text-[10px] font-mono">
    <span className="text-text-muted">{label}</span>
    <div className="flex items-center gap-1">
      <Circle
        size={6}
        className={ok ? 'text-bull fill-bull' : 'text-bear fill-bear'}
      />
      <span className={ok ? 'text-bull' : 'text-bear'}>{ok ? '运行中' : '已停止'}</span>
    </div>
  </div>
);

const StatusDot: React.FC<{ ok: boolean; title: string }> = ({ ok, title }) => (
  <div
    title={title}
    className={`w-2 h-2 rounded-full ${ok ? 'bg-bull shadow-[0_0_4px_#00d395]' : 'bg-bear shadow-[0_0_4px_#f6465d]'}`}
  />
);

// ─── main layout ──────────────────────────────────────────────────────────────

interface LayoutProps {
  children: React.ReactNode;
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const Layout: React.FC<LayoutProps> = ({ children, activeView, onViewChange }) => {
  const [collapsed, setCollapsed] = useState(false);
  const [mode, setMode] = useState<SystemState>(SystemState.SHADOW);

  return (
    <div className="h-screen flex flex-col bg-terminal-bg overflow-hidden">
      {/* Top bar */}
      <TopBar
        sidebarCollapsed={collapsed}
        onToggleSidebar={() => setCollapsed((c) => !c)}
        systemMode={mode}
        onToggleMode={() => setMode((m) => m === SystemState.SHADOW ? SystemState.LIVE : SystemState.SHADOW)}
      />

      {/* Body: sidebar + content */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar collapsed={collapsed} activeView={activeView} onViewChange={onViewChange} />

        {/* Content area */}
        <main className="flex-1 overflow-y-auto p-5">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
