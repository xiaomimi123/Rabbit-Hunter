/**
 * 风控宪法实时状态条 — UI 签名元素之一。
 * 7 个 pip 对应宪法 7 条铁律 (docs/risk-constitution-audit.md)。
 * 数据来自 /api/v5/dashboard/trader-kpi 的 constitution.rule_*。
 *
 *   ok    — sage(gain) 绿,守约
 *   warn  — amber 黄,生效中(默认关闭、锁仓等"非违反但生效")
 *   off   — 灰,未启用 / 数据缺
 */
import { useV5TraderKpi } from '../../hooks/api/useV5TraderKpi';
import type { ConstitutionStatus } from '../../hooks/api/useV5TraderKpi';

type PipState = 'ok' | 'warn' | 'off';

interface Pip {
  num: string;
  title: string;
  state: PipState;
  detail: string;
}

function buildPips(c: ConstitutionStatus | undefined): Pip[] {
  if (!c) {
    return [1, 2, 3, 4, 5, 6, 7].map((n) => ({
      num: String(n),
      title: `规则 ${n}`,
      state: 'off' as PipState,
      detail: '数据加载中',
    }));
  }
  return [
    {
      num: '①',
      title: '单笔风险 ≤ 1%',
      state: c.rule_1_risk_cap_ok ? 'ok' : 'warn',
      detail: c.rule_1_risk_cap_ok ? '守约' : 'config.risk_per_trade 超 1%',
    },
    {
      num: '②',
      title: '进场必挂止损',
      state: c.rule_2_sl_attached.ok ? 'ok' : 'warn',
      detail: `今日 ${c.rule_2_sl_attached.today_sl_attached}/${c.rule_2_sl_attached.today_opens}`,
    },
    {
      num: '③',
      title: '日内 -3% 锁仓',
      state: c.rule_3_daily_dd.lockdown_triggered ? 'warn' : 'ok',
      detail: c.rule_3_daily_dd.lockdown_triggered
        ? '已触发锁仓'
        : `余 ${(c.rule_3_daily_dd.distance_pct * 100).toFixed(2)}%`,
    },
    {
      num: '④',
      title: '杠杆 3-5x 反推',
      state: c.rule_4_leverage_in_range ? 'ok' : 'warn',
      detail: `当前 ${c.rule_4_leverage_value}x`,
    },
    {
      num: '⑤',
      title: 'SL 1.5-2.2×ATR',
      state: c.rule_5_sl_atr_ratio.ok ? 'ok' : 'warn',
      detail: `${c.rule_5_sl_atr_ratio.today_in_range}/${c.rule_5_sl_atr_ratio.today_opens} 落区间`,
    },
    {
      num: '⑥',
      title: '做空默认关闭',
      state: c.rule_6_short_disabled ? 'warn' : 'ok', // warn=生效中(刻意关闭)
      detail: c.rule_6_short_disabled
        ? `生效中 · 今日拦 ${c.rule_6_today_blocked}`
        : '已解锁 SHORT',
    },
    {
      num: '⑦',
      title: '杀手 setup 禁用',
      state: c.rule_7_killer_disabled ? 'ok' : 'warn',
      detail: `今日拦 ${c.rule_7_today_blocked}`,
    },
  ];
}

const STATE_BG: Record<PipState, string> = {
  ok: 'bg-gradient-to-b from-gain to-[#2f8c64]',
  warn: 'bg-gradient-to-b from-amber to-amber-dim',
  off: 'bg-[#2a3340]',
};

export function ConstitutionStrip() {
  const kpi = useV5TraderKpi(30, 24);
  const pips = buildPips(kpi.data?.constitution);
  const okCount = pips.filter((p) => p.state === 'ok').length;
  const total = pips.length;
  const allOk = okCount === total;

  return (
    <div className="flex items-center gap-3.5">
      <span className="text-[10px] uppercase tracking-[0.1em] text-v3faint">
        风控宪法
      </span>
      <div className="flex gap-[5px]">
        {pips.map((p, i) => (
          <div key={i} className="group relative">
            <span
              className={`block w-[9px] h-[18px] rounded-[2px] ${STATE_BG[p.state]}`}
              aria-label={`${p.num} ${p.title}`}
            />
            {/* tooltip */}
            <div
              className="pointer-events-none absolute bottom-full left-1/2 mb-1.5 z-50
                         -translate-x-1/2 whitespace-nowrap
                         rounded-md border border-line bg-[#05080c] px-2 py-1.5 text-[11px]
                         text-v3text opacity-0 transition group-hover:opacity-100"
            >
              {p.num} {p.title} · {p.detail}
            </div>
          </div>
        ))}
      </div>
      <span
        className={`text-xs font-semibold ${allOk ? 'text-gain' : 'text-amber'}`}
      >
        {okCount}/{total} 守约
      </span>
    </div>
  );
}
