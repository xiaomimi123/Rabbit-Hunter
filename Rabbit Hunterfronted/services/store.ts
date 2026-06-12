import { create } from 'zustand';
import type { Mode, AIProvider, WsEvent, Interval } from '../types';

interface UIState {
  sidebarCollapsed: boolean;
  expandedSignalIds: Set<number>;
  selectedSymbolForChart: string | null;
  recentWsEvents: WsEvent[];
  systemMode: Mode | null;
  effectiveAiProvider: AIProvider | null;
  themePreference: 'auto' | 'dark';
  klineInterval: Interval;

  toggleSidebar: () => void;
  toggleSignalExpanded: (id: number) => void;
  setSelectedSymbol: (sym: string | null) => void;
  pushWsEvent: (ev: WsEvent) => void;
  popWsEvent: () => void;
  setSystemMode: (m: Mode) => void;
  setEffectiveAiProvider: (p: AIProvider | null) => void;
  setKlineInterval: (i: Interval) => void;
}

const MAX_WS_QUEUE = 20;

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  expandedSignalIds: new Set(),
  selectedSymbolForChart: null,
  recentWsEvents: [],
  systemMode: null,
  effectiveAiProvider: null,
  themePreference: 'auto',
  klineInterval: '15m',

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  toggleSignalExpanded: (id) =>
    set((s) => {
      const next = new Set(s.expandedSignalIds);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { expandedSignalIds: next };
    }),

  setSelectedSymbol: (sym) => set({ selectedSymbolForChart: sym }),

  pushWsEvent: (ev) =>
    set((s) => {
      const next = [...s.recentWsEvents, ev];
      while (next.length > MAX_WS_QUEUE) next.shift();
      return { recentWsEvents: next };
    }),

  popWsEvent: () =>
    set((s) => ({ recentWsEvents: s.recentWsEvents.slice(1) })),

  setSystemMode: (m) => set({ systemMode: m }),
  setEffectiveAiProvider: (p) => set({ effectiveAiProvider: p }),
  setKlineInterval: (i) => set({ klineInterval: i }),
}));
