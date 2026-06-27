/**
 * HistoryPage — V3 重写 (2026-06-27)。
 *
 * 双栏: 本地交易历史 + 信号扫描历史。
 */
import { useV5OrderHistory } from '../../hooks/api/useV5OrderHistory';
import { useV5Signals } from '../../hooks/api/useV5Signals';
import { blockReasonZh } from '../pages/_signal_helpers';

function Card({ children, className = '', pad0 = false }: { children: React.ReactNode; className?: string; pad0?: boolean }) {
  return (
    <section className={`rounded-[10px] border border-line-soft bg-panel ${pad0 ? 'p-0 overflow-hidden' : 'p-4'} ${className}`}>
      {children}
    </section>
  );
}

function Badge({ tone, children }: { tone: 'long' | 'short' | 'amber' | 'mute'; children: React.ReactNode }) {
  const map = {
    long:  'text-gain bg-gain/10 border border-gain/30',
    short: 'text-loss bg-loss/10 border border-loss/30',
    amber: 'text-amber bg-amber-soft border border-amber/30',
    mute:  'text-v3muted bg-[#1a232d] border border-line',
  };
  return (
    <span className={`text-[10.5px] px-1.5 py-0.5 rounded font-semibold tracking-[0.02em] ${map[tone]}`}>
      {children}
    </span>
  );
}

function SymbolCell({ symbol }: { symbol: string }) {
  const base = symbol.replace('USDT', '').replace('/', '').slice(0, 2).toUpperCase();
  return (
    <div className="flex items-center gap-2 font-semibold text-[12px]">
      <span className="w-[20px] h-[20px] rounded bg-raised grid place-items-center text-[9.5px] font-bold text-v3muted">{base}</span>
      {symbol.replace('USDT', '').replace('/', '')}
    </div>
  );
}

export function HistoryPage() {
  const orders = useV5OrderHistory(200);
  const signals = useV5Signals(200, { side: null, showExecutedOnly: false });

  const closedOrders = (orders.data ?? []).filter((o: any) => o.exit_time);
  const sigList = signals.data?.signals ?? [];

  return (
    <div className="px-6 pb-10 pt-5">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3.5">
        {/* ── 本地交易历史 ────────────────────────────────── */}
        <Card pad0>
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">本地交易历史</h3>
            <span className="text-[10px] text-v3faint font-mono">{closedOrders.length} 笔已平仓</span>
          </div>
          {closedOrders.length === 0 ? (
            <div className="py-10 text-center text-sm text-v3faint">无平仓记录</div>
          ) : (
            <div className="max-h-[680px] overflow-y-auto">
              <table className="w-full font-mono text-[12px]">
                <thead className="text-[10px] uppercase tracking-[0.07em] text-v3faint sticky top-0 bg-panel">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 text-left font-normal">时间</th>
                    <th className="px-3 py-2 text-left font-normal">标的</th>
                    <th className="px-3 py-2 text-left font-normal">方向</th>
                    <th className="px-3 py-2 text-left font-normal">出场</th>
                    <th className="px-3 py-2 text-right font-normal">PnL %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {closedOrders.slice(0, 100).map((o: any) => {
                    const pnlPct = o.pnl_pct ?? 0;
                    const isWin = pnlPct > 0;
                    return (
                      <tr key={o.id} className="text-v3text">
                        <td className="px-3 py-2 text-v3faint text-[11px]">
                          {o.exit_time ? new Date(o.exit_time).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>
                        <td className="px-3 py-2"><SymbolCell symbol={o.symbol} /></td>
                        <td className="px-3 py-2">
                          <Badge tone={o.side === 'LONG' ? 'long' : 'short'}>
                            {o.side === 'LONG' ? '做多' : '做空'}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-v3faint text-[11px]">{o.exit_reason ?? '—'}</td>
                        <td className={`px-3 py-2 text-right ${isWin ? 'text-gain' : 'text-loss'}`}>
                          {isWin ? '+' : ''}{pnlPct.toFixed(2)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* ── 信号扫描历史 ────────────────────────────────── */}
        <Card pad0>
          <div className="flex items-center justify-between px-4 pt-4 pb-2">
            <h3 className="text-xs font-medium text-v3muted uppercase tracking-[0.06em]">信号扫描历史</h3>
            <span className="text-[10px] text-v3faint font-mono">{sigList.length} 条</span>
          </div>
          {sigList.length === 0 ? (
            <div className="py-10 text-center text-sm text-v3faint">无信号记录</div>
          ) : (
            <div className="max-h-[680px] overflow-y-auto">
              <table className="w-full font-mono text-[12px]">
                <thead className="text-[10px] uppercase tracking-[0.07em] text-v3faint sticky top-0 bg-panel">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 text-left font-normal">时间</th>
                    <th className="px-3 py-2 text-left font-normal">标的</th>
                    <th className="px-3 py-2 text-left font-normal">方向</th>
                    <th className="px-3 py-2 text-right font-normal">15m Δ</th>
                    <th className="px-3 py-2 text-right font-normal">RSI</th>
                    <th className="px-3 py-2 text-left font-normal">结果</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line-soft">
                  {sigList.slice(0, 100).map((s: any) => {
                    const delta = (s.delta_15m_pct ?? 0) * 100;
                    const rsi = s.rsi_15m ?? 0;
                    const reasonLabel = s.executed
                      ? '已执行'
                      : (s.block_reason ? (blockReasonZh(s.block_reason) ?? s.block_reason) : '未交易');
                    const tone: 'long' | 'amber' | 'mute' = s.executed
                      ? 'long'
                      : (s.should_trade ? 'amber' : 'mute');
                    return (
                      <tr key={s.id} className="text-v3text">
                        <td className="px-3 py-2 text-v3faint text-[11px]">
                          {s.created_at ? new Date(s.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'}
                        </td>
                        <td className="px-3 py-2"><SymbolCell symbol={s.symbol} /></td>
                        <td className="px-3 py-2">
                          {s.side ? (
                            <Badge tone={s.side === 'LONG' ? 'long' : 'short'}>
                              {s.side === 'LONG' ? '多' : '空'}
                            </Badge>
                          ) : <span className="text-v3faint">—</span>}
                        </td>
                        <td className={`px-3 py-2 text-right ${delta >= 0 ? 'text-gain' : 'text-loss'}`}>
                          {delta >= 0 ? '+' : ''}{delta.toFixed(2)}%
                        </td>
                        <td className="px-3 py-2 text-right text-v3muted">{rsi.toFixed(1)}</td>
                        <td className="px-3 py-2">
                          <Badge tone={tone}>{reasonLabel}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
