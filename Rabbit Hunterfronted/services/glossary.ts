export interface GlossaryEntry {
  key: string;
  zh: string;
  en?: string;
  desc: string;
  category: '仓位' | '指标' | '信号' | 'AI' | '平仓原因' | '统计';
  example?: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  SL: {
    key: 'SL', zh: '止损价', en: 'Stop Loss', category: '仓位',
    desc: '触发自动平仓的价格,限制最大亏损。SHORT 单 SL 在入场价上方,LONG 单在下方。',
    example: 'SHORT 入场 0.166,SL=0.169 → 涨到 0.169 立刻平仓,认亏 1.8%',
  },
  TP: {
    key: 'TP', zh: '止盈价', en: 'Take Profit', category: '仓位',
    desc: '触发自动平仓的价格,锁定盈利。SHORT 单 TP 在入场价下方,LONG 单在上方。',
    example: 'SHORT 入场 0.166,TP=0.162 → 跌到 0.162 自动落袋,赚 2.4%',
  },
  Size: {
    key: 'Size', zh: '仓位大小', en: 'Position Size (USDT)', category: '仓位',
    desc: '这一笔投入的 USDT 金额(账户面值)。结合杠杆放大实际控制金额。',
    example: '15 USDT × 10× 杠杆 = 实际控制 150 USDT 的币',
  },
  Leverage: {
    key: 'Leverage', zh: '杠杆', en: 'Leverage', category: '仓位',
    desc: '把仓位金额放大的倍数。10× 表示 1 USDT 自己的钱可以控制 10 USDT 的币。',
  },
  PnL: {
    key: 'PnL', zh: '盈亏', en: 'Profit and Loss', category: '仓位',
    desc: '当前的浮动盈亏。+1.44% 表示账面赚 1.44%,折算 0.22 USDT。',
  },
  Extension: {
    key: 'Extension', zh: '续仓', en: 'Extension', category: '仓位',
    desc: 'AI 在 15 分钟软目标到点时决定继续持有的次数。最多 3 次,超出强制平。',
  },
  RSI: {
    key: 'RSI', zh: '相对强弱指数', en: 'Relative Strength Index', category: '指标',
    desc: '14 周期。>70 超买(可能见顶反弹),<30 超卖(可能见底反弹)。',
  },
  MACD: {
    key: 'MACD', zh: '指数平滑异同移动平均线', en: 'MACD', category: '指标',
    desc: '快慢 EMA(12/26)的差值与信号线(9 EMA)对比,反映趋势动量变化。',
  },
  'MACD hist': {
    key: 'MACD hist', zh: 'MACD 柱状图', en: 'MACD Histogram', category: '指标',
    desc: 'MACD 减去信号线。正数=多头动能,负数=空头动能。',
    example: '由正→负 = 死叉拐点(开空信号);负→正 = 金叉拐点(开多信号)',
  },
  ATR: {
    key: 'ATR', zh: '平均真实波幅', en: 'Average True Range', category: '指标',
    desc: '14 周期价格平均波动幅度。系统用 ATR 动态计算 SL/TP 距离。',
    example: 'SL 距离 = ATR × 1.5,TP 距离 = ATR × 2.5',
  },
  ΔP15m: {
    key: 'ΔP15m', zh: '15 分钟涨跌幅', en: 'Δ Price 15min', category: '指标',
    desc: '过去 15 分钟的价格变化百分比,代表短期动量。',
  },
  '4h 参考': {
    key: '4h 参考', zh: '4 小时参考', en: '4-hour reference', category: '指标',
    desc: '同样的 RSI/MACD 但用 4 小时周期,确认大趋势是否一致。',
  },
  AND: {
    key: 'AND', zh: 'AND 合谋', en: 'AND-conjunction', category: '信号',
    desc: 'RSI 极端 + MACD 拐点 两个条件同时满足才开单。单一条件不够。',
  },
  score: {
    key: 'score', zh: '综合评分', en: 'Signal score', category: '信号',
    desc: 'AI 置信度 × 仓位倍数 × 50 + AND 加分(20)。0-100。',
  },
  RR: {
    key: 'RR', zh: '风报比', en: 'Risk-Reward Ratio', category: '信号',
    desc: 'TP 距离 ÷ SL 距离。系统默认 2.5 / 1.5 ≈ 1.67,即输 1 块要能赢 1.67 块才开仓。',
  },
  Confidence: {
    key: 'Confidence', zh: 'AI 置信度', en: 'AI Confidence', category: 'AI',
    desc: 'AI 对这笔交易的信心 (0-1)。越高越确定,但不代表必赢。',
  },
  'SL Multiplier': {
    key: 'SL Multiplier', zh: 'SL 调整倍数', en: 'SL Multiplier', category: 'AI',
    desc: 'AI 在系统默认 SL 距离上的调整。1.0 = 不变,>1 = 放宽,<1 = 收紧。',
  },
  'TP Multiplier': {
    key: 'TP Multiplier', zh: 'TP 调整倍数', en: 'TP Multiplier', category: 'AI',
    desc: 'AI 在系统默认 TP 距离上的调整。1.0 = 不变,>1 = 拉更远,<1 = 提前止盈。',
  },
  'Size Multiplier': {
    key: 'Size Multiplier', zh: 'Size 调整倍数', en: 'Size Multiplier', category: 'AI',
    desc: 'AI 在系统默认仓位上的调整。0.5 = 半仓,1.5 = 加码。',
  },
  RAG: {
    key: 'RAG', zh: '检索增强生成', en: 'Retrieval-Augmented Generation', category: 'AI',
    desc: 'AI 检索本地历史上类似的 setup,把结果作为推理依据。',
    example: '当前 RSI=72 hist=-0.0006 → 找到 5 个相似 case,4 个 WIN → AI 倾向于批准',
  },
  'Top-1 distance': {
    key: 'Top-1 distance', zh: '最相似距离', en: 'Top-1 Distance', category: 'AI',
    desc: '当前 setup 与历史最相似 case 的加权欧氏距离。越小越像。<0.1 是高度相似。',
  },
  TP_HIT: {
    key: 'TP_HIT', zh: '触及止盈', en: 'Take-Profit Hit', category: '平仓原因',
    desc: '价格走到 TP 位置,自动平仓获利。',
  },
  SL_HIT: {
    key: 'SL_HIT', zh: '触及止损', en: 'Stop-Loss Hit', category: '平仓原因',
    desc: '价格走到 SL 位置,自动平仓认亏。',
  },
  SOFT_TARGET_REACHED: {
    key: 'SOFT_TARGET_REACHED', zh: '软目标到时', en: 'Soft target reached', category: '平仓原因',
    desc: '默认 15 分钟持仓时间到,平仓。AI 可决定续仓延长。',
  },
  SIGNAL_REVERSE: {
    key: 'SIGNAL_REVERSE', zh: '信号反转', en: 'Signal Reversed', category: '平仓原因',
    desc: '指标方向反转(RSI 回到中性 或 MACD 反向拐点),自动平仓。仅对自动单生效。',
  },
  AI_EXTEND_MAX: {
    key: 'AI_EXTEND_MAX', zh: '续仓用完', en: 'AI extension maxed', category: '平仓原因',
    desc: 'AI 已经续仓 3 次,系统强制平仓。',
  },
  MANUAL_USER: {
    key: 'MANUAL_USER', zh: '用户手动平', en: 'Manual close by user', category: '平仓原因',
    desc: '你点了"立即平"按钮。',
  },
  'Profit Factor': {
    key: 'Profit Factor', zh: '盈亏比', en: 'Profit Factor', category: '统计',
    desc: '总盈利 ÷ 总亏损。>1 净赚,<1 净亏,>2 优秀。',
  },
  Funnel: {
    key: 'Funnel', zh: '信号漏斗', en: 'Signal Funnel', category: '统计',
    desc: 'Scanner 扫到 → 通过 AND → 实际开仓,展示信号在每一层的过滤情况。',
  },
  failure_mode: {
    key: 'failure_mode', zh: '失败模式', en: 'Failure Mode', category: 'AI',
    desc: 'AI 对这笔交易失败原因的分类,来自预置 8 种 + 新提案的 taxonomy。命中已知失败模式的新 setup 会被入场层 veto。',
  },
  reflection: {
    key: 'reflection', zh: '复盘', en: 'Reflection', category: 'AI',
    desc: '每笔关仓后,AI 用 5 问结构(为什么开 / 怎么想 / 实际怎么走 / 哪种失败 / 下次怎么改)分析,作为下次决策的 RAG 输入。',
  },
  realized_r: {
    key: 'realized_r', zh: '实际 R 倍', en: 'Realized R-multiple', category: '统计',
    desc: '盈亏百分比 ÷ SL 距离百分比。+1 = 触发 TP,-1 = 触发 SL。是跨币种比较交易质量的标准单位。',
  },
  setup_type: {
    key: 'setup_type', zh: 'Setup 类型', en: 'Setup Type', category: '信号',
    desc: '入场时根据 RSI 状态 × MACD 状态 × 方向(可能加 funding)派生的桶名。所有聚合按它分类。',
  },
};

export const GLOSSARY_CATEGORIES: Array<{ name: GlossaryEntry['category']; label: string }> = [
  { name: '仓位', label: '仓位术语' },
  { name: '指标', label: '技术指标' },
  { name: '信号', label: '信号 & 决策' },
  { name: 'AI', label: 'AI 相关' },
  { name: '平仓原因', label: '平仓原因' },
  { name: '统计', label: '统计指标' },
];
