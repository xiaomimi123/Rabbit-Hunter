/**
 * Layout v45 — "简约高级" 风格
 *
 *   ┌──────────────────────────────────────────┐
 *   │ Top bar 56px                              │
 *   ├────────┬─────────────────────────────────┤
 *   │ Side   │  Content (overflow-y auto)       │
 *   │ 232px  │                                  │
 *   │ → 64   │                                  │
 *   └────────┴─────────────────────────────────┘
 *
 * 设计原则：
 *   - 单 accent（amber）、单层 surface、hairline 边
 *   - 无 emoji、无 neon glow、无装饰渐变
 *   - SHADOW/LIVE 切换走 useUIStore（之前只在 local state，对其它页无效）
 *   - 切到 LIVE 走 ConfirmModal 二次确认（用户曾因误点引爆真实下单）
 */

import React, { useState } from 'react';
import {
  ChevronLeft, ChevronRight, Circle, AlertTriangle, Loader2,
  CrosshairIcon, LayoutGrid, Briefcase, SquarePen,
  Cpu, Sliders, BarChart3, ScrollText, Cog,
} from 'lucide-react';
import { ViewType, SystemState } from '../types';
import { useUIStore } from '../services/store';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { useExchange } from '../hooks/useExchange';
import { useSystemMode } from '../hooks/useSystemMode';
import { toast } from './Toast';
import ConfirmModal from './ui/ConfirmModal';

// ─── nav config ──────────────────────────────────────────────────────────────

interface NavItem {
  id: ViewType;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string; strokeWidth?: number | string }>;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: '交易',
    items: [
      { id: 'KILL_BOARD', label: '信号',     icon: CrosshairIcon },
      { id: 'POSITIONS',  label: '持仓',     icon: Briefcase },
      { id: 'ORDER',      label: '手动下单', icon: SquarePen },
    ],
  },
  {
    label: '智能',
    items: [
      { id: 'AI_STATUS',       label: 'AI 状态',  icon: Cpu },
      { id: 'WEIGHT_HISTORY',  label: '权重历史', icon: ScrollText },
      { id: 'TRADE_SCORES',    label: '评分',     icon: BarChart3 },
      { id: 'STRATEGY_CONFIG', label: '策略',     icon: Sliders },
    ],
  },
  {
    label: '系统',
    items: [
      { id: 'DASHBOARD', label: '概览', icon: LayoutGrid },
      { id: 'SETTINGS',  label: '设置', icon: Cog },
    ],
  },
];

// ─── top bar ─────────────────────────────────────────────────────────────────

interface TopBarProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  systemMode: SystemState;
  onRequestModeChange: (target: SystemState) => void;
}

const TopBar: React.FC<TopBarProps> = ({
  sidebarCollapsed, onToggleSidebar, systemMode, onRequestModeChange,
}) => (
  <header className="h-14 flex items-center justify-between px-5 bg-terminal-bg border-b border-terminal-border shrink-0 z-20">
    {/* Left: brand */}
    <div className="flex items-center gap-4">
      <button
        onClick={onToggleSidebar}
        className="p-1.5 -ml-1.5 rounded text-text-muted hover:text-text-primary hover:bg-terminal-hover transition-colors"
        aria-label={sidebarCollapsed ? '展开导航' : '收起导航'}
      >
        {sidebarCollapsed ? <ChevronRight size={16} strokeWidth={1.5} /> : <ChevronLeft size={16} strokeWidth={1.5} />}
      </button>
      <div className="flex items-baseline gap-2">
        <span className="text-[15px] font-medium text-text-primary tracking-tight">
          Rabbit Hunter
        </span>
        <span className="text-[10px] text-text-muted font-mono tracking-micro">v5.0</span>
      </div>
    </div>

    {/* Right: active exchange badge + SHADOW/LIVE switch */}
    <div className="flex items-center gap-3">
      <ExchangeBadge />
      <ModeSwitch mode={systemMode} onRequestChange={onRequestModeChange} />
    </div>
  </header>
);

// ─── exchange badge ─────────────────────────────────────────────────────────

const ExchangeBadge: React.FC = () => {
  const { data, isLoading } = useExchange();
  if (isLoading || !data) {
    return (
      <div className="inline-flex items-center px-2 py-1 rounded border border-terminal-border text-text-muted text-[10px] uppercase tracking-micro num">
        …
      </div>
    );
  }
  const isOkx = data.exchange === 'okx';
  // 配色：OKX 暖琥珀 accent；Binance 用中性 — 区分但不刺眼
  const tone = isOkx
    ? 'bg-primary/10 border-primary/30 text-primary'
    : 'bg-white/[0.04] border-white/10 text-text-secondary';
  return (
    <div
      title={`信号源 + 交易所: ${data.label}${data.testnet ? '（测试网）' : ''}`}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded border ${tone} text-[10px] uppercase tracking-micro font-medium`}
    >
      <span>{data.label}</span>
      {data.testnet && (
        <span className="text-warn text-[9px]">·TEST</span>
      )}
    </div>
  );
};

// ─── mode switch ─────────────────────────────────────────────────────────────

interface ModeSwitchProps {
  mode: SystemState;
  onRequestChange: (target: SystemState) => void;
}

const ModeSwitch: React.FC<ModeSwitchProps> = ({ mode, onRequestChange }) => {
  // 视觉：两段式 segmented，hover/active 都很克制
  return (
    <div className="inline-flex items-center rounded border border-terminal-border bg-terminal-card overflow-hidden">
      <button
        onClick={() => mode !== SystemState.SHADOW && onRequestChange(SystemState.SHADOW)}
        className={`px-3 py-1.5 text-[11px] uppercase tracking-micro transition-colors ${
          mode === SystemState.SHADOW
            ? 'bg-warn/15 text-warn'
            : 'text-text-muted hover:text-text-secondary'
        }`}
      >
        影子
      </button>
      <div className="w-px h-4 bg-terminal-border" />
      <button
        onClick={() => mode !== SystemState.LIVE && onRequestChange(SystemState.LIVE)}
        className={`px-3 py-1.5 text-[11px] uppercase tracking-micro transition-colors ${
          mode === SystemState.LIVE
            ? 'bg-bear/15 text-bear'
            : 'text-text-muted hover:text-text-secondary'
        }`}
      >
        实盘
      </button>
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
      className={`flex flex-col bg-terminal-bg border-r border-terminal-border transition-all duration-200 shrink-0 ${
        collapsed ? 'w-16' : 'w-[232px]'
      }`}
    >
      <nav className="flex-1 overflow-y-auto py-5 px-3 space-y-6">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            {!collapsed && (
              <div className="px-2 mb-2 text-[10px] text-text-muted uppercase tracking-micro">
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
                    className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-md transition-colors ${
                      active
                        ? 'bg-primary/10 text-primary'
                        : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
                    }`}
                  >
                    <item.icon
                      size={16}
                      strokeWidth={1.6}
                      className="shrink-0"
                    />
                    {!collapsed && (
                      <span className="text-[13px] truncate">{item.label}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* footer status */}
      <div className={`border-t border-terminal-border ${collapsed ? 'py-3 flex flex-col items-center gap-2' : 'px-4 py-3 space-y-2'}`}>
        {collapsed ? (
          <>
            <StatusDot ok={collectorRunning} title="采集器" />
            <StatusDot ok={apiOnline} title="API" />
          </>
        ) : (
          <>
            <StatusRow label="采集器" ok={collectorRunning} />
            <StatusRow label="API"   ok={apiOnline} />
          </>
        )}
      </div>
    </aside>
  );
};

const StatusRow: React.FC<{ label: string; ok: boolean }> = ({ label, ok }) => (
  <div className="flex items-center justify-between text-[11px]">
    <span className="text-text-muted">{label}</span>
    <div className="flex items-center gap-1.5">
      <Circle size={6} className={ok ? 'text-bull fill-bull' : 'text-bear fill-bear'} />
      <span className={`num ${ok ? 'text-bull' : 'text-bear'}`}>
        {ok ? '运行' : '停止'}
      </span>
    </div>
  </div>
);

const StatusDot: React.FC<{ ok: boolean; title: string }> = ({ ok, title }) => (
  <div
    title={title}
    className={`w-2 h-2 rounded-full ${ok ? 'bg-bull' : 'bg-bear'}`}
  />
);

// ─── WS 连接状态 banner（v45）────────────────────────────────────────────────

const WsStatusBanner: React.FC = () => {
  const status = useUIStore((s) => s.wsStatus);
  const attempts = useUIStore((s) => s.wsReconnectAttempts);
  const lastConnectedAt = useUIStore((s) => s.wsLastConnectedAt);

  // connected / idle 都不展示（idle 表示尚未尝试连接，没必要恐吓）
  if (status === 'connected' || status === 'idle') return null;

  const lastConnectedHint = lastConnectedAt
    ? ` · 上次连接 ${Math.max(1, Math.round((Date.now() - lastConnectedAt) / 1000))} 秒前`
    : '';

  if (status === 'connecting') {
    return (
      <div className="px-8 py-2 text-[12px] text-text-secondary border-b border-terminal-border bg-terminal-card flex items-center gap-2">
        <Loader2 size={12} strokeWidth={1.6} className="animate-spin text-primary" />
        <span>正在连接实时推送…</span>
      </div>
    );
  }
  if (status === 'reconnecting') {
    return (
      <div className="px-8 py-2 text-[12px] text-warn border-b border-warn/30 bg-warn/5 flex items-center gap-2">
        <AlertTriangle size={12} strokeWidth={1.6} />
        <span>
          实时推送已断开，正在重连（第 {attempts} 次）{lastConnectedHint} —
          页面上的数据可能不是最新。
        </span>
      </div>
    );
  }
  // failed
  return (
    <div className="px-8 py-2 text-[12px] text-bear border-b border-bear/30 bg-bear/5 flex items-center gap-2">
      <AlertTriangle size={12} strokeWidth={1.6} />
      <span>
        实时推送连接失败{lastConnectedHint} — 价格/持仓显示的是最后一次同步的快照，
        交易决策请刷新页面或核对后端日志后再做。
      </span>
    </div>
  );
};

// ─── main layout ─────────────────────────────────────────────────────────────

interface LayoutProps {
  children: React.ReactNode;
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const Layout: React.FC<LayoutProps> = ({ children, activeView, onViewChange }) => {
  const [collapsed, setCollapsed] = useState(false);

  // v0.5.4: SHADOW/LIVE 状态走后端 API（DB 持久化），不再仅 localStorage
  const { mode, setMode } = useSystemMode();
  const systemState = mode === 'LIVE' ? SystemState.LIVE : SystemState.SHADOW;

  // v0.5.5: active exchange label，给 ConfirmModal 显示真实 broker
  const { data: exchangeInfo } = useExchange();
  const exLabel = exchangeInfo?.label ?? '...';

  const [pendingLive, setPendingLive] = useState(false);

  const requestModeChange = (target: SystemState) => {
    if (target === SystemState.LIVE) {
      setPendingLive(true);
    } else {
      // LIVE → SHADOW 直接降级（安全方向，不弹确认）
      setMode.mutate('SHADOW', {
        onSuccess: () => toast.success('已切换到影子模式 — 信号会写虚拟仓位'),
        onError:   (e: any) => toast.error(`切换失败: ${e?.message ?? e}`),
      });
    }
  };

  const confirmLive = () => {
    setMode.mutate('LIVE', {
      onSuccess: () => {
        toast.success('已切换到实盘 — 信号将下真实订单');
        setPendingLive(false);
      },
      onError: (e: any) => {
        toast.error(e?.response?.detail ?? e?.message ?? '切换失败');
        setPendingLive(false);
      },
    });
  };

  return (
    <div className="h-screen flex flex-col bg-terminal-bg overflow-hidden">
      <TopBar
        sidebarCollapsed={collapsed}
        onToggleSidebar={() => setCollapsed((c) => !c)}
        systemMode={systemState}
        onRequestModeChange={requestModeChange}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar collapsed={collapsed} activeView={activeView} onViewChange={onViewChange} />
        <main className="flex-1 overflow-y-auto">
          <WsStatusBanner />
          <div className="max-w-[1440px] mx-auto px-8 py-8">
            {children}
          </div>
        </main>
      </div>

      <ConfirmModal
        open={pendingLive}
        title="切换到实盘模式"
        description={`开启后，信号将下达真实订单到当前 active exchange (${exLabel})。后端会先检查 API key 是否能鉴权 — 如果失败会拒绝切换。`}
        details={[
          { label: '当前模式', value: '影子',  tone: 'warn' },
          { label: '目标模式', value: '实盘',  tone: 'bear' },
        ]}
        confirmLabel="切换到实盘"
        cancelLabel="保持影子"
        destructive
        loading={setMode.isPending}
        onConfirm={confirmLive}
        onCancel={() => setPendingLive(false)}
      />
    </div>
  );
};

export default Layout;
