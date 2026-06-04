/**
 * OpenAI AI 层状态面板 (v5.0)
 *
 * 显示：
 * - OpenAI Assistant 连接状态
 * - 交易决策统计 (通过 / 拒绝)
 * - Vector Store 记忆统计 (胜率、交易数、上次上传)
 * - 手动触发记忆上传按钮
 * - 系统健康状态
 */

import React, { useState } from 'react';
import {
  BrainCircuit, Activity, Upload, RefreshCw,
  CheckCircle, XCircle, AlertCircle, Zap, Database,
} from 'lucide-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiStatusAPI } from '../services/api';
import { toast } from './Toast';
import { InlineSpinner } from '../ui/LoadingSkeleton';

// ─── data hook ───────────────────────────────────────────────────────────────

function useOpenAIStatus() {
  return useQuery({
    queryKey: ['openai-status'],
    queryFn: () => aiStatusAPI.getStatus(),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

// ─── sub-components ──────────────────────────────────────────────────────────

interface CardProps {
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  iconColor: string;
  borderColor: string;
  children: React.ReactNode;
}

function Card({ title, icon: Icon, iconColor, borderColor, children }: CardProps) {
  return (
    <div className={`bg-terminal-card border ${borderColor} rounded-xl p-5`}>
      <div className="flex items-center gap-2.5 mb-4">
        <Icon size={18} className={iconColor} />
        <h3 className="text-sm font-bold text-text-primary font-mono">{title}</h3>
      </div>
      {children}
    </div>
  );
}

interface RowProps {
  label: string;
  children: React.ReactNode;
}

function Row({ label, children }: RowProps) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-terminal-border/50 last:border-0">
      <span className="text-xs text-text-secondary">{label}</span>
      <span className="text-xs font-mono">{children}</span>
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono border ${
      ok
        ? 'bg-bull/10 text-bull border-bull/30'
        : 'bg-bear/10 text-bear border-bear/30'
    }`}>
      {ok ? <CheckCircle size={9} /> : <XCircle size={9} />}
      {ok ? '正常' : '未就绪'}
    </span>
  );
}

// ─── main component ──────────────────────────────────────────────────────────

export default function AIStatus() {
  const queryClient = useQueryClient();
  const { data: resp, isLoading, isFetching, refetch } = useOpenAIStatus();
  const ai = resp?.data;

  const uploadMutation = useMutation({
    mutationFn: () => aiStatusAPI.uploadMemory(),
    onSuccess: () => {
      toast.success('记忆上传完成，AI 将在下次决策时使用最新数据');
      queryClient.invalidateQueries({ queryKey: ['openai-status'] });
    },
    onError: (err: any) => {
      toast.error(`上传失败: ${err?.message ?? err}`);
    },
  });

  const log = ai?.trade_log ?? {};
  const winRate: number = log.win_rate ?? 0;
  const winRateColor = winRate >= 60 ? 'text-bull' : winRate >= 45 ? 'text-warn' : 'text-bear';

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-text-primary font-mono">
            AI 决策层
            {isFetching && <InlineSpinner className="ml-2" />}
          </h1>
          <p className="text-[11px] text-text-muted font-mono mt-0.5">
            OpenAI GPT-4o · Assistants API · Vector Store 持续学习
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="px-3 py-1.5 bg-terminal-card border border-terminal-border rounded text-xs font-mono text-text-secondary hover:bg-terminal-hover transition-colors flex items-center gap-1.5 disabled:opacity-40"
        >
          <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-text-muted text-sm font-mono">
          加载中...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

          {/* OpenAI 连接状态 */}
          <Card
            title="OpenAI Assistant"
            icon={BrainCircuit}
            iconColor="text-primary"
            borderColor={ai?.configured ? 'border-primary/30' : 'border-terminal-border'}
          >
            <div className="space-y-0">
              <Row label="启用状态">
                <StatusDot ok={ai?.enabled ?? false} />
              </Row>
              <Row label="API Key">
                <StatusDot ok={ai?.has_api_key ?? false} />
              </Row>
              <Row label="Assistant 配置">
                <StatusDot ok={ai?.configured ?? false} />
              </Row>
              <Row label="模型">
                <span className="text-text-primary">{ai?.model ?? '—'}</span>
              </Row>
              {ai?.assistant_id_masked && (
                <Row label="Assistant ID">
                  <span className="text-text-muted">{ai.assistant_id_masked}</span>
                </Row>
              )}
              {ai?.vector_store_id_masked && (
                <Row label="Vector Store">
                  <span className="text-text-muted">{ai.vector_store_id_masked}</span>
                </Row>
              )}
            </div>

            {!ai?.configured && (
              <div className="mt-3 flex items-start gap-2 bg-warn/5 border border-warn/20 rounded-lg p-3">
                <AlertCircle size={13} className="text-warn mt-0.5 shrink-0" />
                <p className="text-[11px] text-warn/80 font-mono leading-relaxed">
                  运行 <code className="bg-terminal-border/50 px-1 rounded">python scripts/ai/setup_assistant.py</code> 完成初始化，并将 ID 填入 .env
                </p>
              </div>
            )}
          </Card>

          {/* 交易记忆统计 */}
          <Card
            title="Vector Store 记忆"
            icon={Database}
            iconColor="text-info"
            borderColor="border-info/20"
          >
            <div className="space-y-0">
              <Row label="历史交易数">
                <span className="text-text-primary">{log.total ?? 0} 笔</span>
              </Row>
              <Row label="盈利">
                <span className="text-bull">{log.wins ?? 0} 笔</span>
              </Row>
              <Row label="亏损">
                <span className="text-bear">{log.losses ?? 0} 笔</span>
              </Row>
              <Row label="胜率">
                <span className={`font-bold ${winRateColor}`}>{winRate.toFixed(1)}%</span>
              </Row>
              <Row label="最后更新">
                <span className="text-text-muted">{log.last_updated ?? '—'}</span>
              </Row>
            </div>

            {/* 胜率进度条 */}
            {(log.total ?? 0) > 0 && (
              <div className="mt-3">
                <div className="h-1.5 bg-terminal-border rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      winRate >= 60 ? 'bg-bull' : winRate >= 45 ? 'bg-warn' : 'bg-bear'
                    }`}
                    style={{ width: `${Math.min(100, winRate)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1">
                  <span>0%</span>
                  <span>胜率 {winRate.toFixed(1)}%</span>
                  <span>100%</span>
                </div>
              </div>
            )}

            {/* 上传按钮 */}
            <button
              onClick={() => uploadMutation.mutate()}
              disabled={uploadMutation.isPending || !ai?.configured}
              className="mt-4 w-full flex items-center justify-center gap-2 px-3 py-2 text-xs font-mono bg-primary/10 text-primary border border-primary/30 rounded-lg hover:bg-primary/20 transition-colors disabled:opacity-40"
            >
              {uploadMutation.isPending
                ? <><InlineSpinner /> 上传中...</>
                : <><Upload size={12} /> 立即上传记忆到 Vector Store</>
              }
            </button>
          </Card>

          {/* 工作原理说明 */}
          <Card
            title="AI 决策流程"
            icon={Zap}
            iconColor="text-warn"
            borderColor="border-terminal-border"
          >
            <div className="space-y-2.5 text-[11px] font-mono text-text-secondary">
              {[
                ['1', '规则引擎', '扫描 → 评分 → SNIPER / VULTURE 策略路由'],
                ['2', 'AI 审查', 'GPT-4o 检索相似历史 + 当前信号综合判断'],
                ['3', '参数调优', 'AI 建议 SL/TP 倍数 (受 guardrails 限幅)'],
                ['4', '下单执行', 'BinanceTrader 执行，SL/TP 由 AI 参数决定'],
                ['5', '学习闭环', '平仓后结果写入日志，定期上传 Vector Store'],
              ].map(([num, title, desc]) => (
                <div key={num} className="flex gap-3">
                  <span className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    {num}
                  </span>
                  <div>
                    <span className="text-text-primary font-bold">{title}</span>
                    <span className="text-text-muted ml-2">{desc}</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Guardrails 参数说明 */}
          <Card
            title="Guardrails 限幅规则"
            icon={Activity}
            iconColor="text-bull"
            borderColor="border-terminal-border"
          >
            <div className="space-y-0">
              <Row label="止损 (SL)">
                <span className="text-bear">1.2× — 3.0× ATR</span>
              </Row>
              <Row label="止盈 (TP)">
                <span className="text-bull">2.0× — 6.0× ATR</span>
              </Row>
              <Row label="最低风险收益比">
                <span className="text-text-primary">TP ≥ SL × 1.5</span>
              </Row>
              <Row label="仓位倍数">
                <span className="text-text-primary">0.3× — 1.2×</span>
              </Row>
              <Row label="超时降级">
                <span className="text-text-muted">20 秒后回退规则引擎</span>
              </Row>
            </div>
            <p className="mt-3 text-[10px] text-text-muted font-mono leading-relaxed">
              Guardrails 强制执行，AI 无法突破。确保每笔交易的风险在可控范围内。
            </p>
          </Card>

        </div>
      )}
    </div>
  );
}
