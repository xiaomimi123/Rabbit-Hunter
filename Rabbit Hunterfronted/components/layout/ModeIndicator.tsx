/**
 * 左下角常驻模式指示器 — UI 签名元素之二。
 * SHADOW/LIVE 标签 + 实时纸面 / OKX 权益。
 *
 * 永远可见,因为 "现在是不是真钱" 是最该一直在场的安全状态。
 */
import { useSystemMode } from '../../hooks/useSystemMode';
import { useAccountBalance } from '../../hooks/api/useV5Account';

export function ModeIndicator() {
  const { mode } = useSystemMode();
  const balance = useAccountBalance();
  const isLive = mode === 'LIVE';

  // SHADOW: 纸面权益 = 初始 + 累计已实现 PnL
  // LIVE:   OKX total
  const b = balance.data;
  const equity =
    isLive && b?.status === 'ok'
      ? b.total_usdt
      : (b?.paper_initial_balance_usdt ?? 10000) + (b?.paper_realized_pnl_usdt ?? 0);

  const dollars = Math.floor(equity);
  const cents = (equity - dollars).toFixed(2).slice(1); // ".32"

  const tagColor = isLive
    ? 'text-loss bg-loss/10 border-loss/40'
    : 'text-amber bg-amber-soft border-amber/30';
  const dotColor = isLive ? 'bg-loss shadow-[0_0_7px_var(--tw-shadow-color)] shadow-loss' : 'bg-amber shadow-[0_0_7px_var(--tw-shadow-color)] shadow-amber';

  return (
    <div className="rounded-lg border border-line bg-[#11181F] px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[0.08em] text-v3faint">
          运行模式
        </span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.04em] ${tagColor}`}
        >
          <span className={`block h-1.5 w-1.5 rounded-full ${dotColor}`} />
          {isLive ? 'LIVE' : 'SHADOW'}
        </span>
      </div>
      <div className="mt-2.5 text-[10px] uppercase tracking-[0.08em] text-v3faint">
        {isLive ? 'OKX 账户权益' : '纸面账户权益'}
      </div>
      <div className="mt-1 font-mono text-[17px] font-semibold text-v3text">
        ${dollars.toLocaleString()}
        <span className="text-v3faint">{cents}</span>
      </div>
    </div>
  );
}
