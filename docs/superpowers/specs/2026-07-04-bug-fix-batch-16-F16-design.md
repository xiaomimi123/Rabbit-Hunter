# Bug Fix Batch 16 · Finding 16 · Dashboard 24h PnL 合并 LIVE + paper · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 16 (P1)

---

## 一、问题陈述

`Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts:22-26`:

```ts
const [signals, history, active] = await Promise.all([
  apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
  apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
  apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
]);
```

- history / active 只读 `/api/v5/paper-positions`(paper_trades 表)
- LIVE 模式实交易走 `positions_v5` 表,`/api/v5/positions` 未被 dashboard 消费
- Failure scenario:切换 LIVE 后,LIVE 交易产生真实 PnL 但 Dashboard 显示的 "24h 实现 PnL" 和"胜率"来自同期的 paper_trades(可能为 0 或旧数据),运营看不到 LIVE 表现,风控判断错

## 二、目标

Dashboard 同时拉 paper + live 两路 CLOSED 历史 + OPEN 活仓,**union 合并** 24h 数据。win rate / pnl / holding minutes / active_count 均基于合并结果。用 F15 建立的 `Promise.allSettled` 模式,任一路 API 失败不阻塞。

## 三、范围

**In scope**:
- `Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts`:
  - 5 路 `Promise.allSettled`(signals + paper 历史 + paper 活仓 + live 历史 + live 活仓)
  - 失败源 fallback 空数组
  - closed_24h = paper_closed_24 ⋃ live_closed_24 后再过滤 24h
  - active_count = paper_active.length + live_active.length
  - `DashboardData` 加可选 `errors?: { signals?, paper_history?, live_history?, paper_active?, live_active? }` 字段
- 新单测 `Rabbit Hunterfronted/tests/hooks/useV5Dashboard.test.ts`(3 tests)

**Out of scope**:
- 不改前端 UI(DashboardPage 消费 `pnl_total_usdt` 等,新 errors 字段 additive)
- 不做 mode-aware 路由(改成"总是拉两路"更简单更鲁棒,SHADOW 模式 live 数据自然为空)
- 不改 API 契约
- 不改 refetchInterval(保持 30_000)
- 不改 signals 计算逻辑
- 不加分类 PnL 字段(`pnl_paper_usdt` / `pnl_live_usdt` 后续按需加,YAGNI)

## 四、Change 1 — `DashboardData` interface 加 errors

**Before**:
```ts
export interface DashboardData {
  signals_24h: number;
  ...
  active_count: number;
  closed_24h: V5Position[];
}
```

**After**:
```ts
export interface DashboardData {
  signals_24h: number;
  ...
  active_count: number;
  closed_24h: V5Position[];
  errors?: {
    signals?: string;
    paper_history?: string;
    live_history?: string;
    paper_active?: string;
    live_active?: string;
  };
}
```

## 五、Change 2 — queryFn 5 路 allSettled + 合并

**Before**(L21-66 骨架):
```ts
queryFn: async () => {
  const [signals, history, active] = await Promise.all([
    apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
  ]);
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const in24 = (iso: string | null) => iso ? new Date(iso).getTime() >= cutoff : false;

  const s24 = signals.data.filter(s => in24(s.created_at));
  ...
  const closed24 = history.data.filter(p => in24(p.exit_time));
  ...
  return {
    ...,
    active_count: active.data.length,
    closed_24h: closed24,
  };
}
```

**After**:
```ts
queryFn: async () => {
  const [
    signalsRes,
    paperHistoryRes,
    paperActiveRes,
    liveHistoryRes,
    liveActiveRes,
  ] = await Promise.allSettled([
    apiGet<V5SignalsResponse>('/api/v5/signals?limit=2000'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=CLOSED&limit=500'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
    apiGet<V5PositionsResponse>('/api/v5/positions?status=CLOSED&limit=500'),
    apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
  ]);

  const signalsData = signalsRes.status === 'fulfilled' ? signalsRes.value.data : [];
  const paperHistoryData = paperHistoryRes.status === 'fulfilled' ? paperHistoryRes.value.data : [];
  const paperActiveData = paperActiveRes.status === 'fulfilled' ? paperActiveRes.value.data : [];
  const liveHistoryData = liveHistoryRes.status === 'fulfilled' ? liveHistoryRes.value.data : [];
  const liveActiveData = liveActiveRes.status === 'fulfilled' ? liveActiveRes.value.data : [];

  const errMsg = (r: PromiseSettledResult<unknown>) =>
    r.status === 'rejected'
      ? String((r.reason as any)?.message ?? r.reason ?? 'unknown')
      : undefined;
  const errors: DashboardData['errors'] = {
    signals: errMsg(signalsRes),
    paper_history: errMsg(paperHistoryRes),
    live_history: errMsg(liveHistoryRes),
    paper_active: errMsg(paperActiveRes),
    live_active: errMsg(liveActiveRes),
  };
  const hasAnyError = Object.values(errors).some(v => v !== undefined);

  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const in24 = (iso: string | null) => iso ? new Date(iso).getTime() >= cutoff : false;

  const s24 = signalsData.filter(s => in24(s.created_at));
  const passedAnd = s24.filter(s => s.should_trade === 1);
  const executed = s24.filter(s => s.executed === 1);

  const blockCounts: Record<string, number> = {};
  for (const s of s24) {
    const k = s.block_reason || (s.executed === 1 ? 'EXECUTED' : (s.should_trade === 1 ? 'NONE' : 'OTHER'));
    blockCounts[k] = (blockCounts[k] ?? 0) + 1;
  }

  // F16: paper + live 合并 24h CLOSED
  const closed24 = [...paperHistoryData, ...liveHistoryData].filter(p => in24(p.exit_time));

  const wins = closed24.filter(p => (p.pnl_pct ?? 0) > 0).length;
  const winRate = closed24.length > 0 ? wins / closed24.length : 0;
  const pnlSum = closed24.reduce((acc, p) => acc + (p.pnl_usdt ?? 0), 0);
  const pnlPctSum = closed24.reduce((acc, p) => acc + (p.pnl_pct ?? 0), 0);
  const avgHold = closed24.length > 0
    ? closed24.reduce((acc, p) => {
        if (!p.entry_time || !p.exit_time) return acc;
        const mins = (new Date(p.exit_time).getTime() - new Date(p.entry_time).getTime()) / 60_000;
        return acc + mins;
      }, 0) / closed24.length
    : 0;

  return {
    signals_24h: s24.length,
    signals_passed_and: passedAnd.length,
    signals_executed: executed.length,
    signals_block_counts: blockCounts,
    win_rate_24h: winRate,
    pnl_total_usdt: pnlSum,
    pnl_total_pct: pnlPctSum,
    avg_holding_minutes: avgHold,
    active_count: paperActiveData.length + liveActiveData.length,
    closed_24h: closed24,
    errors: hasAnyError ? errors : undefined,
  };
},
```

## 六、Change 3 — 新单测 `tests/hooks/useV5Dashboard.test.ts`

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5Dashboard } from '@/hooks/api/useV5Dashboard';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  };
}

const nowIso = () => new Date().toISOString();

// 24h 内的 CLOSED 交易, pnl_usdt / pnl_pct 由 caller 决定
const mkClosed = (id: number, pnlUsdt: number, pnlPct: number) => ({
  id,
  symbol: `SYM${id}/USDT`,
  side: 'LONG',
  status: 'CLOSED',
  entry_price: 100,
  entry_time: nowIso(),
  exit_price: 105,
  exit_time: nowIso(),
  pnl_usdt: pnlUsdt,
  pnl_pct: pnlPct,
  extension_count: 0,
} as any);

const mkOpen = (id: number) => ({
  id,
  symbol: `SYM${id}/USDT`,
  side: 'LONG',
  status: 'OPEN',
  extension_count: 0,
} as any);

describe('useV5Dashboard', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('merges paper + live for 24h stats and active_count', async () => {
    (fetch as any)
      // signals
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      // paper CLOSED: 2 wins pnl 5 + 3, avg
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 5, 0.02), mkClosed(2, 3, 0.01)] }),
        { status: 200 }))
      // paper OPEN
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(10)] }), { status: 200 }))
      // live CLOSED: 1 loss -2, 1 win 4
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(3, -2, -0.01), mkClosed(4, 4, 0.03)] }),
        { status: 200 }))
      // live OPEN
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(11), mkOpen(12)] }), { status: 200 }));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(4);      // paper 2 + live 2
    expect(d.pnl_total_usdt).toBe(10);         // 5+3-2+4
    expect(d.active_count).toBe(3);            // paper 1 + live 2
    expect(d.win_rate_24h).toBeCloseTo(3 / 4); // 3 wins / 4
    expect(d.errors).toBeUndefined();
  });

  it('degrades gracefully when live endpoints fail', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 5, 0.02)] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(10)] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('503 live history'))
      .mockRejectedValueOnce(new Error('503 live active'));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(1);       // 只有 paper
    expect(d.pnl_total_usdt).toBe(5);
    expect(d.active_count).toBe(1);
    expect(d.errors?.live_history).toContain('503');
    expect(d.errors?.live_active).toContain('503');
    expect(d.errors?.paper_history).toBeUndefined();
    expect(result.current.isError).toBe(false);
  });

  it('degrades gracefully when paper endpoints fail', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('timeout paper history'))
      .mockRejectedValueOnce(new Error('timeout paper active'))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkClosed(1, 7, 0.05)] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkOpen(20), mkOpen(21)] }), { status: 200 }));

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5Dashboard(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    const d = result.current.data!;
    expect(d.closed_24h.length).toBe(1);       // 只有 live
    expect(d.pnl_total_usdt).toBe(7);
    expect(d.active_count).toBe(2);
    expect(d.errors?.paper_history).toContain('timeout');
    expect(d.errors?.paper_active).toContain('timeout');
    expect(d.errors?.live_history).toBeUndefined();
  });
});
```

## 七、验收标准

- `cd "Rabbit Hunterfronted" && npm test -- tests/hooks/useV5Dashboard.test.ts` → 3/3 pass
- 邻近回归:`useV5Signals`, `useV5WebSocket`, `useV5ManualOrder`, `useV5ActivePositions`(F15) 无回归
- `grep -c "Promise.allSettled" "Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts"` → 1
- `grep -cE "Promise\.all\b" "Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts"` → 0
- `grep -c "positions?status=CLOSED\|positions?status=OPEN" "Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts"` → 4(2 paper + 2 live)
- 只 stage 2 文件
- Commit subject EXACT: `fix(useV5Dashboard): 合并 paper + live 24h PnL / 活仓 + errors 字段 (Finding 16)`

## 八、失效模式

- **5 路都失败**:signals=0, closed=[], active_count=0, errors 全填。React Query 不失败,前端看到"空盘"+5 个 error。可接受(refetch 30s 内自愈)
- **paper 端点返 SHADOW 期数据但 mode 已切 LIVE**:paper 老数据仍在 24h 窗口内 → 合并进 pnl 统计。这**是 by-design**:union 就是"最近 24h 所有 CLOSED",不区分模式。若未来需要分离,加 `pnl_paper` / `pnl_live` split
- **`positions_v5` 表在测试 DB 未 mig**:`/api/v5/positions?status=CLOSED` 返 500 → 走 allSettled 兜住,`live_history_error` 填。等价 test 2 场景
- **API 契约变更 `.data` 不存在**:`.value.data` 抛 → TypeError,但 allSettled 只捕获 rejected 不捕获 sync throw?实际上 `.value` 是 apiGet 的 Promise resolved 值,`.data` 是同步字段访问 —— 若 apiGet resolve 到无 `.data` 对象,访问 `.data` 返 undefined 而非抛。用 `.data ?? []` 兜(**加**:`.value.data ?? []`)

## 九、超范围声明

- 不改前端 UI 消费者
- 不加 mode-aware 路由(简单 union 已够)
- 不加分类 PnL 字段
- 不改 refetchInterval

## 十、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 16 (P1)
- 引用:
  - `Rabbit Hunterfronted/hooks/api/useV5Dashboard.ts:22-26`(现只查 paper)
  - `api/routes/positions.py:15-22`(paper + live 两端点均已存在)
- 相关 Finding:F15(Batch 15, allSettled 模式建立)、F12(Batch 12, LIVE 平仓端点)
