import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore } from '@/services/store';

describe('UIStore', () => {
  beforeEach(() => {
    useUIStore.setState({
      sidebarCollapsed: false,
      expandedSignalIds: new Set(),
      selectedSymbolForChart: null,
      recentWsEvents: [],
      systemMode: null,
      effectiveAiProvider: null,
      themePreference: 'auto',
      klineInterval: '15m',
    });
  });

  it('toggleSidebar flips bool', () => {
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it('toggleSignalExpanded adds and removes id', () => {
    useUIStore.getState().toggleSignalExpanded(42);
    expect(useUIStore.getState().expandedSignalIds.has(42)).toBe(true);
    useUIStore.getState().toggleSignalExpanded(42);
    expect(useUIStore.getState().expandedSignalIds.has(42)).toBe(false);
  });

  it('pushWsEvent appends and caps queue at 20', () => {
    for (let i = 0; i < 25; i++) {
      useUIStore.getState().pushWsEvent({ type: 'ping', ts: i } as any);
    }
    expect(useUIStore.getState().recentWsEvents.length).toBe(20);
    expect(useUIStore.getState().recentWsEvents[0]).toMatchObject({ ts: 5 });
  });

  it('popWsEvent removes oldest', () => {
    useUIStore.getState().pushWsEvent({ type: 'ping', ts: 1 } as any);
    useUIStore.getState().pushWsEvent({ type: 'ping', ts: 2 } as any);
    useUIStore.getState().popWsEvent();
    expect(useUIStore.getState().recentWsEvents.length).toBe(1);
    expect(useUIStore.getState().recentWsEvents[0]).toMatchObject({ ts: 2 });
  });

  it('setSystemMode updates value', () => {
    useUIStore.getState().setSystemMode('LIVE');
    expect(useUIStore.getState().systemMode).toBe('LIVE');
  });
});
