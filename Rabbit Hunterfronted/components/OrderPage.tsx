/**
 * OrderPage v45 — 重写
 *
 * 旧版 743 行：
 *   - symbol 下拉读 store.killQueue（noop shim 永远空）
 *   - leverage / risk 用 Number(e.target.value) → 空字符串变 0 → 提交除零
 *   - "执行"用 native confirm()，没显示 notional / 风险预算
 *   - 包含 chart / market depth 两块独立功能，让单页过度膨胀
 *
 * 重写：
 *   - 用 useKillQueue 拿真实 symbol 列表
 *   - 数值用受控字符串 + onBlur clamp + 提交前 parseFloat 校验，杜绝 NaN
 *   - 走 ConfirmModal，露出 notional + 风险预算 + 实/影子模式
 *   - 不再画 chart / market depth（独立页另做）
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, ShieldCheck, AlertTriangle, Lightbulb } from 'lucide-react';
import { tradeAPI, accountAPI, entryValidationAPI } from '../services/api';
import { useKillQueue } from '../hooks/useKillQueue';
import { useSystemMode } from '../hooks/useSystemMode';
import {
  Card, EmptyState, NumberCell, Pill, SectionHeader, StatTile,
} from './ui/Primitives';
import ConfirmModal from './ui/ConfirmModal';

// ─── helpers ──────────────────────────────────────────────────────────────────

function toFiniteNumber(s: string): number | null {
  if (s.trim() === '') return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// ─── component ────────────────────────────────────────────────────────────────

const OrderPage: React.FC = () => {
  const { isLive } = useSystemMode();

  // form state — 数字用字符串，提交时再 parse（防 NaN 直接提交）
  const [symbol, setSymbol] = useState<string>('');
  const [side, setSide] = useState<'LONG' | 'SHORT'>('LONG');
  const [type, setType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [leverageStr, setLeverageStr] = useState<string>('10');
  const [riskStr, setRiskStr] = useState<string>('2');
  const [limitPriceStr, setLimitPriceStr] = useState<string>('');

  // server state
  const { data: signals = [], isLoading: signalsLoading } = useKillQueue(50, 0);
  const [balance, setBalance] = useState<{ balance: number; freeMargin?: number } | null>(null);

  // flow state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [validating, setValidating] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // 默认 symbol：第一条信号
  useEffect(() => {
    if (!symbol && signals.length) {
      setSymbol(signals[0].symbol || '');
    }
  }, [signals, symbol]);

  // 首次拉余额
  useEffect(() => {
    let mounted = true;
    accountAPI.getBalance().then((b) => mounted && setBalance(b));
    return () => { mounted = false; };
  }, []);

  // parsed numbers
  const leverage = useMemo(() => {
    const n = toFiniteNumber(leverageStr);
    return n == null ? null : clamp(n, 1, 125);
  }, [leverageStr]);

  const risk = useMemo(() => {
    const n = toFiniteNumber(riskStr);
    return n == null ? null : clamp(n, 0.01, 10);
  }, [riskStr]);

  const limitPrice = useMemo(() => toFiniteNumber(limitPriceStr), [limitPriceStr]);

  // notional 估算
  const notional = useMemo(() => {
    if (!balance?.balance || !leverage || !risk) return null;
    return (balance.balance * risk / 100) * leverage;
  }, [balance, leverage, risk]);

  // ── 表单可提交校验 ────────────────────────────────────────
  const formError = useMemo(() => {
    if (!symbol) return '请选择交易对';
    if (leverage == null) return '杠杆无效';
    if (risk == null) return '风险百分比无效';
    if (type === 'LIMIT' && (limitPrice == null || limitPrice <= 0)) return '限价单需要有效限价';
    return null;
  }, [symbol, leverage, risk, type, limitPrice]);

  // ── actions ──────────────────────────────────────────────
  const onValidate = async () => {
    if (formError) { setError(formError); return; }
    setValidating(true); setError(null); setValidationResult(null);
    try {
      const r = await entryValidationAPI.validate(symbol, leverage!, risk!);
      setValidationResult(r);
    } catch (e: any) {
      setError(e?.message ?? '校验失败');
    } finally {
      setValidating(false);
    }
  };

  const onExecuteRequest = () => {
    if (formError) { setError(formError); return; }
    setError(null);
    setConfirmOpen(true);
  };

  const onExecuteConfirm = async () => {
    setExecuting(true); setError(null);
    try {
      const r = await tradeAPI.execute({
        symbol,
        side,
        leverage: leverage!,
        riskPercentage: risk!,
        orderType: type,
        limitPrice: type === 'LIMIT' ? limitPrice ?? undefined : undefined,
        validateWithAI: true,
      });
      setExecutionResult(r);
      setConfirmOpen(false);
    } catch (e: any) {
      setError(e?.message ?? '下单失败');
    } finally {
      setExecuting(false);
    }
  };

  // ── render ───────────────────────────────────────────────
  return (
    <div className="space-y-8">
      {/* hero */}
      <header>
        <div className="label-sm mb-1">手动下单</div>
        <h1 className="text-[22px] font-medium text-text-primary tracking-tight">
          构建一笔信号外的交易
        </h1>
        {!isLive && (
          <div className="mt-2 inline-flex items-center gap-2 text-[12px] text-warn">
            <AlertTriangle size={14} strokeWidth={1.6} />
            当前为影子模式 — 提交不会真实下单
          </div>
        )}
      </header>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* form */}
        <Card className="lg:col-span-2 p-6">
          <SectionHeader title="订单参数" subtitle="所有数值在提交前会被校验和钳制" />

          <div className="space-y-5 mt-4">
            {/* symbol */}
            <Field label="交易对">
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="w-full"
                disabled={signalsLoading}
              >
                {signalsLoading && <option value="">加载中…</option>}
                {!signalsLoading && !signals.length && <option value="">暂无可选</option>}
                {signals.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol}
                    {s.final_score ? ` · ${(s.final_score > 1 ? s.final_score : s.final_score * 100).toFixed(0)}` : ''}
                  </option>
                ))}
              </select>
            </Field>

            {/* side + type */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="方向">
                <Segment
                  options={[
                    { value: 'LONG',  label: '做多' },
                    { value: 'SHORT', label: '做空' },
                  ]}
                  value={side}
                  onChange={setSide as any}
                />
              </Field>
              <Field label="订单类型">
                <Segment
                  options={[
                    { value: 'MARKET', label: '市价' },
                    { value: 'LIMIT',  label: '限价' },
                  ]}
                  value={type}
                  onChange={setType as any}
                />
              </Field>
            </div>

            {/* leverage + risk */}
            <div className="grid grid-cols-2 gap-3">
              <Field label="杠杆 (1–125)">
                <input
                  type="text"
                  inputMode="numeric"
                  value={leverageStr}
                  onChange={(e) => setLeverageStr(e.target.value)}
                  onBlur={() => {
                    const n = toFiniteNumber(leverageStr);
                    if (n != null) setLeverageStr(String(clamp(n, 1, 125)));
                  }}
                  className="w-full"
                  placeholder="10"
                />
              </Field>
              <Field label="风险 % (0.01–10)">
                <input
                  type="text"
                  inputMode="decimal"
                  value={riskStr}
                  onChange={(e) => setRiskStr(e.target.value)}
                  onBlur={() => {
                    const n = toFiniteNumber(riskStr);
                    if (n != null) setRiskStr(String(clamp(n, 0.01, 10)));
                  }}
                  className="w-full"
                  placeholder="2"
                />
              </Field>
            </div>

            {/* limit price */}
            {type === 'LIMIT' && (
              <Field label="限价">
                <input
                  type="text"
                  inputMode="decimal"
                  value={limitPriceStr}
                  onChange={(e) => setLimitPriceStr(e.target.value)}
                  placeholder="0.0"
                  className="w-full"
                />
              </Field>
            )}

            {/* errors */}
            {error && (
              <div className="flex items-center gap-2 text-[12px] text-bear">
                <AlertTriangle size={14} strokeWidth={1.6} />
                {error}
              </div>
            )}

            {/* actions */}
            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={onValidate}
                disabled={validating || !!formError}
                className="btn-ghost"
              >
                {validating ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} strokeWidth={1.7} />}
                校验
              </button>
              <button
                onClick={onExecuteRequest}
                disabled={!!formError}
                className={isLive ? 'btn-bear' : 'btn-primary'}
              >
                {isLive ? '下单（实盘）' : '下单（影子）'}
              </button>
            </div>
          </div>
        </Card>

        {/* preview */}
        <div className="space-y-3">
          <StatTile
            label="账户余额"
            value={balance?.balance ? (
              <NumberCell value={balance.balance} decimals={2} suffix=" USDT" className="text-2xl" />
            ) : '—'}
            hint={balance?.freeMargin != null ? `可用 ${balance.freeMargin.toFixed(2)}` : undefined}
          />
          <StatTile
            label="预估 Notional"
            value={notional != null ? (
              <NumberCell value={notional} decimals={2} suffix=" USDT" className="text-2xl" />
            ) : '—'}
            hint={leverage != null && risk != null
              ? `${risk.toFixed(2)}% × ${leverage}x`
              : '请填完杠杆和风险'}
          />
          <StatTile
            label="风险预算"
            value={balance?.balance && risk != null ? (
              <NumberCell
                value={balance.balance * risk / 100}
                decimals={2}
                suffix=" USDT"
                className="text-2xl"
              />
            ) : '—'}
            hint="单笔最大亏损上限"
          />

          {validationResult && (
            <Card className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb size={14} strokeWidth={1.7} className="text-primary" />
                <div className="text-[12px] font-medium text-text-primary">校验结果</div>
              </div>
              <pre className="text-[11px] text-text-secondary font-mono whitespace-pre-wrap leading-relaxed">
                {JSON.stringify(validationResult, null, 2)}
              </pre>
            </Card>
          )}

          {executionResult && (
            <Card className="p-4">
              <div className="flex items-center gap-2 mb-2">
                <Pill tone={executionResult.success ? 'bull' : 'bear'}>
                  {executionResult.success ? '已下单' : '失败'}
                </Pill>
              </div>
              <pre className="text-[11px] text-text-secondary font-mono whitespace-pre-wrap leading-relaxed">
                {JSON.stringify(executionResult, null, 2)}
              </pre>
            </Card>
          )}

          {!validationResult && !executionResult && (
            <EmptyState title="尚未提交订单" hint="先做一次校验，然后下单" />
          )}
        </div>
      </section>

      {/* confirm */}
      <ConfirmModal
        open={confirmOpen}
        title="确认下单"
        description={isLive
          ? '此操作将向 Binance 提交真实订单，无法撤回。'
          : '当前为影子模式，订单不会真实成交。'}
        details={[
          { label: '交易对', value: symbol },
          { label: '方向',   value: side === 'LONG' ? '做多' : '做空',
            tone: side === 'LONG' ? 'bull' : 'bear' },
          { label: '订单类型', value: type === 'MARKET' ? '市价' : `限价 @ ${limitPriceStr}` },
          { label: '杠杆',     value: leverage ? `${leverage}x` : '—' },
          { label: '风险',     value: risk != null ? `${risk.toFixed(2)}%` : '—' },
          { label: 'Notional', value: notional != null ? notional.toFixed(2) + ' USDT' : '—' },
          { label: '模式',     value: isLive ? '实盘' : '影子', tone: isLive ? 'bear' : 'warn' },
        ]}
        confirmLabel={isLive ? '提交实盘订单' : '提交影子订单'}
        cancelLabel="取消"
        destructive={isLive}
        loading={executing}
        onConfirm={onExecuteConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
};

// ─── small bits ───────────────────────────────────────────────────────────────

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="label-sm block mb-1.5">{label}</label>
    {children}
  </div>
);

interface SegmentProps<T extends string> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}

function Segment<T extends string>({ options, value, onChange }: SegmentProps<T>) {
  return (
    <div className="inline-flex w-full rounded border border-terminal-border overflow-hidden">
      {options.map((opt, i) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`flex-1 px-3 py-2 text-[12px] transition-colors ${
              active
                ? 'bg-primary/12 text-primary'
                : 'text-text-secondary hover:bg-terminal-hover hover:text-text-primary'
            } ${i > 0 ? 'border-l border-terminal-border' : ''}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export default OrderPage;
