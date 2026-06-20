import { FlaskConical, Terminal, Github } from 'lucide-react';
import { SectionTitle } from '../primitives-v3/SectionTitle';
import { Card } from '../primitives-v3/Card';
import { Alert } from '../primitives-v3/Alert';

export function BacktestPage() {
  return (
    <div className="space-y-6">
      <SectionTitle
        title="策略验证"
        subtitle="Walk-forward 回测 + 多策略对比"
      />

      <Alert tone="warning">
        回测引擎当前以 CLI 形式提供,Web UI 接入计划中。先在仓库根目录运行 <code className="font-mono text-amber-200">scripts/backtest.py</code>。
      </Alert>

      <Card title="如何运行" subtitle="本地命令">
        <div className="space-y-4">
          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 font-mono text-sm text-zinc-300">
            <div className="text-xs text-zinc-500 mb-2"># 单 symbol 回测</div>
            <div>$ python -m scripts.backtest \</div>
            <div className="pl-4">--symbol BTC/USDT \</div>
            <div className="pl-4">--strategy v5_rsi_macd \</div>
            <div className="pl-4">--start-date 2026-04-01 \</div>
            <div className="pl-4">--end-date 2026-06-01</div>
          </div>

          <div className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 font-mono text-sm text-zinc-300">
            <div className="text-xs text-zinc-500 mb-2"># 多 symbol walk-forward</div>
            <div>$ python -m scripts.backtest_walkforward \</div>
            <div className="pl-4">--config configs/exp3b.yml \</div>
            <div className="pl-4">--out reports/exp3b.json</div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <FeatureCard
          icon={<FlaskConical className="h-5 w-5 text-indigo-300" />}
          title="参数搜索"
          desc="逐个扫描 RSI threshold / Δ price / funding |z|"
        />
        <FeatureCard
          icon={<Terminal className="h-5 w-5 text-emerald-300" />}
          title="多 symbol 并行"
          desc="同时回测 BTC / ETH / SOL,生成对比 PnL 曲线"
        />
        <FeatureCard
          icon={<Github className="h-5 w-5 text-amber-300" />}
          title="UI 接入路线图"
          desc="后续把 CLI 抽成 backend endpoint,本页接入参数表单 + 进度条 + 报告"
        />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, desc }: { icon: React.ReactNode; title: string; desc: string }) {
  return (
    <div className="rounded-3xl border border-zinc-800 bg-zinc-900/70 p-5 shadow-[0_24px_80px_rgba(0,0,0,0.25)]">
      <div className="flex items-center gap-2 mb-3">{icon}<div className="font-medium text-zinc-100">{title}</div></div>
      <div className="text-sm text-zinc-400 leading-relaxed">{desc}</div>
    </div>
  );
}
