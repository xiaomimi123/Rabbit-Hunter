# Bug Fix Batch 15 · Finding 15 · useV5ActivePositions Promise.allSettled 降级 · Design

> 日期: 2026-07-04
> 状态: awaiting user review
> 前置: `docs/audit-2026-07/bug-fix-list.md` Finding 15 (P1)

---

## 一、问题陈述

`Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts:16-19`:

```ts
const [live, paper] = await Promise.all([
  apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
  apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
]);
```

- `Promise.all` fail-fast:任一 rejected → 整个 queryFn 抛,React Query 转 error 态,`data` 变 `undefined`
- 消费者:OverviewPage / PortfolioPage / ReliabilityPage / DiagnosticsPage 用 `active.data?.combined ?? []` —— 走 `[]` 降级,但**看不到另一类可用仓位**
- Failure scenario:API 服务器重启中 LIVE 端点 503,paper 端点仍 200 → Dashboard 显示"加载失败",运营看不到任何 paper 持仓,虽然 paper 完全 OK

## 二、目标

改 `Promise.allSettled`,任一失败不阻塞另一类。`CombinedActive` 加 `live_error?: string`、`paper_error?: string`;失败源 fallback `[]` 并写 error 字段。前端可选消费(现有消费者无 error 字段访问 → 无 regression;后续加降级提示时再消费)。

## 三、范围

**In scope**:
- `Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts` 用 `Promise.allSettled`
- `CombinedActive` interface 加两个可选 error 字段
- 新增 `Rabbit Hunterfronted/tests/hooks/useV5ActivePositions.test.ts`(3 tests)

**Out of scope**:
- 不改前端 UI 组件(OverviewPage / PortfolioPage 等)—— 新字段 additive,现有消费者无感
- 不改 `useV5ClosePosition`(同文件里,不涉及本 Finding)
- 不改后端 API 契约
- 不改错误重试策略(React Query 层保留)
- 不加全局 error boundary / toast

## 四、Change 1 — `CombinedActive` interface 加字段

**Before**:
```ts
interface CombinedActive {
  live: V5Position[];
  paper: V5Position[];
  combined: V5Position[];
  total: number;
}
```

**After**:
```ts
interface CombinedActive {
  live: V5Position[];
  paper: V5Position[];
  combined: V5Position[];
  total: number;
  live_error?: string;
  paper_error?: string;
}
```

## 五、Change 2 — queryFn 用 `Promise.allSettled`

**Before**:
```ts
queryFn: async () => {
  const [live, paper] = await Promise.all([
    apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
  ]);
  return {
    live: live.data,
    paper: paper.data,
    combined: [...live.data, ...paper.data],
    total: live.data.length + paper.data.length,
  };
},
```

**After**:
```ts
queryFn: async () => {
  const [liveResult, paperResult] = await Promise.allSettled([
    apiGet<V5PositionsResponse>('/api/v5/positions?status=OPEN'),
    apiGet<V5PositionsResponse>('/api/v5/paper-positions?status=OPEN'),
  ]);
  const live = liveResult.status === 'fulfilled' ? liveResult.value.data : [];
  const paper = paperResult.status === 'fulfilled' ? paperResult.value.data : [];
  const live_error = liveResult.status === 'rejected'
    ? String(liveResult.reason?.message ?? liveResult.reason ?? 'unknown')
    : undefined;
  const paper_error = paperResult.status === 'rejected'
    ? String(paperResult.reason?.message ?? paperResult.reason ?? 'unknown')
    : undefined;
  return {
    live,
    paper,
    combined: [...live, ...paper],
    total: live.length + paper.length,
    live_error,
    paper_error,
  };
},
```

## 六、Change 3 — 新单测 `tests/hooks/useV5ActivePositions.test.ts`

复用现有 pattern(useV5Signals.test.ts):

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useV5ActivePositions } from '@/hooks/api/useV5ActivePositions';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    wrapper: ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: qc }, children),
  };
}

const mkPos = (id: number, side: 'LIVE' | 'PAPER') =>
  ({ id, symbol: `SYM${id}/USDT`, side: 'LONG', status: 'OPEN', _kind: side } as any);

describe('useV5ActivePositions', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('merges live + paper when both succeed', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'LIVE')] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(2, 'PAPER'), mkPos(3, 'PAPER')] }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.total).toBe(3);
    expect(result.current.data!.live).toHaveLength(1);
    expect(result.current.data!.paper).toHaveLength(2);
    expect(result.current.data!.live_error).toBeUndefined();
    expect(result.current.data!.paper_error).toBeUndefined();
  });

  it('degrades gracefully when live fails, paper succeeds', async () => {
    (fetch as any)
      .mockRejectedValueOnce(new Error('503 Service Unavailable'))
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'PAPER')] }), { status: 200 }));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.live).toEqual([]);
    expect(result.current.data!.paper).toHaveLength(1);
    expect(result.current.data!.total).toBe(1);
    expect(result.current.data!.live_error).toContain('503');
    expect(result.current.data!.paper_error).toBeUndefined();
    // isError 保持 false —— 部分降级不算 query 失败
    expect(result.current.isError).toBe(false);
  });

  it('degrades gracefully when paper fails, live succeeds', async () => {
    (fetch as any)
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ status: 'success', data: [mkPos(1, 'LIVE')] }), { status: 200 }))
      .mockRejectedValueOnce(new Error('timeout'));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useV5ActivePositions(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeTruthy());
    expect(result.current.data!.live).toHaveLength(1);
    expect(result.current.data!.paper).toEqual([]);
    expect(result.current.data!.total).toBe(1);
    expect(result.current.data!.live_error).toBeUndefined();
    expect(result.current.data!.paper_error).toContain('timeout');
  });
});
```

## 七、验收标准

- `cd "Rabbit Hunterfronted" && npm test -- tests/hooks/useV5ActivePositions.test.ts` → 3/3 pass
- 邻近回归:`tests/hooks/useV5Signals.test.ts`、`tests/hooks/useV5WebSocket.test.ts`、`tests/hooks/useV5ManualOrder.test.ts` 无回归
- `grep -c "Promise.allSettled" "Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts"` → 1
- `grep -c "Promise.all\b" "Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts"` → 0(注意 `\b` 排除 allSettled)
- `grep -c "live_error\|paper_error" "Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts"` → ≥4(interface 2 + return 2)
- 只 stage 2 文件(`Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts` + `Rabbit Hunterfronted/tests/hooks/useV5ActivePositions.test.ts`)
- Commit subject EXACT: `fix(useV5ActivePositions): Promise.allSettled + live_error/paper_error 降级字段 (Finding 15)`

## 八、失效模式

- **同时 live + paper 都失败**:`combined=[]`,total=0,两个 error 字段都填。React Query 不 error 态(因 queryFn resolved),前端看到"0 持仓 + 两个 error 消息"。可接受:前端后续可根据两 error 显 boundary 或加 retry 按钮。**不改 useV5ClosePosition 里的 invalidateQueries** —— 关仓 mutation 触发 invalidate,新数据仍走 allSettled 逻辑。
- **`reason.message` 可能非 string**:`String(...)` 无条件转,兜住 undefined / non-Error。
- **`refetchInterval: 5_000` 不变**:每 5s 重新拉,error 会在下次 tick 自愈。
- **消费者 combined 长度含 0**:等价于两类都无 OPEN 或都失败;前端已有 `?? []` 兜。

## 九、超范围声明

- 不改 UI 组件(前端可选消费新字段)
- 不改 useV5ClosePosition
- 不改 API 契约
- 不加全局 error boundary / toast
- 不改 refetch 策略 / 重试次数

## 十、相关

- Bug audit: `docs/audit-2026-07/bug-fix-list.md` Finding 15 (P1)
- 引用:
  - `Rabbit Hunterfronted/hooks/api/useV5ActivePositions.ts:16-19`(Promise.all)
  - `Rabbit Hunterfronted/components/pages-v4/OverviewPage.tsx:107`(消费者 combined)
- 相关 Finding:F16 (Dashboard PnL 聚合)—— 前端下一批
