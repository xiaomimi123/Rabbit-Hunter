/**
 * UI-only global state (Zustand).
 * Server data lives in React Query hooks — keep this store pure UI.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { ViewType } from '../types';

export type WsStatus = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'failed';

interface UIStore {
  activeView: ViewType;
  selectedSymbol: string | null;
  expandedSymbols: Set<string>;
  isAnatomyPanelOpen: boolean;
  systemState: 'SHADOW' | 'LIVE';
  // v45: WebSocket 连接状态，给 Layout 顶栏 banner 用
  wsStatus: WsStatus;
  wsLastConnectedAt: number | null;       // epoch ms，banner 用来显示"上次同步 N 秒前"
  wsReconnectAttempts: number;            // 当前尝试次数

  setActiveView: (view: ViewType) => void;
  selectSymbol: (symbol: string | null) => void;
  toggleExpanded: (symbol: string) => void;
  setAnatomyPanelOpen: (open: boolean) => void;
  setSystemState: (state: 'SHADOW' | 'LIVE') => void;
  toggleSystemMode: () => void;
  setWsStatus: (status: WsStatus, attempts?: number) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      activeView: 'KILL_BOARD',
      selectedSymbol: null,
      expandedSymbols: new Set(),
      isAnatomyPanelOpen: false,
      systemState: 'SHADOW',
      wsStatus: 'idle' as WsStatus,
      wsLastConnectedAt: null,
      wsReconnectAttempts: 0,

      setActiveView: (view) => set({ activeView: view }),
      selectSymbol: (symbol) => set({ selectedSymbol: symbol }),
      toggleExpanded: (symbol) =>
        set((s) => {
          const next = new Set(s.expandedSymbols);
          if (next.has(symbol)) next.delete(symbol);
          else next.add(symbol);
          return { expandedSymbols: next };
        }),
      setAnatomyPanelOpen: (open) => set({ isAnatomyPanelOpen: open }),
      setSystemState: (state) => set({ systemState: state }),
      toggleSystemMode: () =>
        set((s) => ({
          systemState: s.systemState === 'SHADOW' ? 'LIVE' : 'SHADOW',
        })),
      setWsStatus: (status, attempts) =>
        set((s) => ({
          wsStatus: status,
          wsReconnectAttempts: attempts ?? s.wsReconnectAttempts,
          wsLastConnectedAt: status === 'connected' ? Date.now() : s.wsLastConnectedAt,
        })),
    }),
    {
      name: 'ui-store',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({
        activeView: s.activeView,
        selectedSymbol: s.selectedSymbol,
        systemState: s.systemState,
      }),
    }
  )
);

// ─── backward-compat shim ────────────────────────────────────────────────────
// Old components (Dashboard, OrderPage, websocket.ts) still call the legacy API.
// All server-data setters are now no-ops since React Query owns that state.

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const _noop = (..._args: any[]): void => {};

function buildLegacyState() {
  const s = useUIStore.getState();
  return {
    ...s,
    // Legacy server-state fields (always empty — use React Query hooks)
    killQueue: [] as any[],
    selectedCoin: null as any,
    killQueueLoading: false,
    positions: [] as any[],
    positionsLoading: false,
    evolutionEvents: [] as any[],
    aiLoading: false,
    systemHealth: 0.99,
    latencyMs: 0,
    // Legacy setters — no-ops (data now in React Query)
    setKillQueue: _noop,
    selectCoin: _noop,
    setKillQueueLoading: _noop,
    setPositions: _noop,
    setPositionsLoading: _noop,
    setSystemState: s.setSystemState,
    setSystemHealth: _noop,
    setLatency: _noop,
    setEvolutionEvents: _noop,
    setAILoading: _noop,
    setActiveView: s.setActiveView,
    setAnatomyPanelOpen: s.setAnatomyPanelOpen,
    toggleSystemMode: s.toggleSystemMode,
    reset: _noop,
  };
}

/** Legacy hook — kept for backward compatibility. New code should use useUIStore. */
export function useV43Store() {
  // Subscribe to the real store so the component re-renders on UI state changes.
  const s = useUIStore();
  return {
    ...buildLegacyState(),
    // Override with live reactive values
    activeView: s.activeView,
    selectedSymbol: s.selectedSymbol,
    isAnatomyPanelOpen: s.isAnatomyPanelOpen,
    systemState: s.systemState,
  };
}

// Attach Zustand-style static method so websocket.ts can call useV43Store.getState()
useV43Store.getState = buildLegacyState;
