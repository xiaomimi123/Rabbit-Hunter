// V5 API types. Field names mirror api/schemas/*.py exactly.
// Time fields are ISO 8601 UTC strings (ensure_utc_iso()).

export type Side = 'LONG' | 'SHORT';
export type Mode = 'SHADOW' | 'LIVE';
export type OutcomeLabel = 'WIN' | 'LOSS' | 'FLAT';
export type EventType = 'entry' | 'exit' | 'extension';
export type Interval = '15m' | '1h' | '4h';
export type AIProvider = 'deepseek' | 'openai';

// ── Signals ──
export interface V5Signal {
  id: number;
  symbol: string;
  created_at: string;
  delta_15m_pct: number;
  volume_24h_usdt: number;
  rsi_15m: number;
  rsi_4h: number | null;
  macd_15m: number;
  macd_signal_15m: number;
  macd_hist_15m: number;
  macd_hist_prev_15m: number;
  macd_hist_4h: number | null;
  atr_15m: number;
  current_price: number;
  should_trade: number;   // 0 | 1
  side: Side | null;
  reasoning: string;
  block_reason: string | null;
  ai_confidence: number | null;
  ai_sl_multiplier: number | null;
  ai_tp_multiplier: number | null;
  ai_size_multiplier: number | null;
  ai_reasoning: string | null;
  entry_price: number | null;
  sl_price: number | null;
  tp_price: number | null;
  size_usdt: number | null;
  expected_rr: number | null;
  executed: number;       // 0 | 1
  position_id: number | null;
}

export interface V5SignalsResponse {
  status: string;
  data: V5Signal[];
}

// ── Positions ──
export interface V5Position {
  id: number;
  symbol: string;
  side: Side;
  status: 'OPEN' | 'CLOSED';
  entry_price: number | null;
  entry_time: string | null;
  sl_price: number | null;
  tp_price: number | null;
  size_usdt: number | null;
  position_size_coins: number | null;
  leverage: number | null;
  target_close_at: string | null;
  extension_count: number;
  entry_rsi_15m: number | null;
  entry_macd_hist_15m: number | null;
  entry_rsi_4h: number | null;
  entry_atr_15m: number | null;
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  pnl_usdt: number | null;
  pnl_pct: number | null;
  holding_minutes: number | null;
  created_at: string | null;
  updated_at: string | null;
  strategy_id: string | null;
}

export interface V5PositionsResponse {
  status: string;
  data: V5Position[];
}

// ── Strategy Config ──
export interface ParamSpec {
  key: string;
  value: number;
  default: number;
  min: number;
  max: number;
  unit: string;
  description: string;
}
export interface StrategyConfigResponse {
  params: ParamSpec[];
}
export interface StrategyConfigPatchRequest {
  [key: string]: number;
}
export interface StrategyConfigPreviewResponse {
  estimated_entries_per_hour: number;
  estimated_win_rate: number;
  note: string;
}

// ── Settings ──
export interface SettingsResponse {
  exchange: string;
  openai_api_key_masked: string;
  openai_assistant_id: string | null;
  openai_vector_store_id: string | null;
  deepseek_api_key_masked: string;
  deepseek_enabled: boolean;
  active_ai_provider: AIProvider | null;
  active_chat_model: string;
  system_mode: Mode;
  enable_auto_trading: boolean;
  ai_fail_open: boolean;
  sl_tp_fail_open: boolean;
}
export interface SettingsPatchRequest {
  exchange?: string;
  openai_api_key?: string;
  openai_assistant_id?: string | null;
  deepseek_api_key?: string;
  deepseek_enabled?: boolean;
  system_mode?: Mode;
  enable_auto_trading?: boolean;
  ai_fail_open?: boolean;
  sl_tp_fail_open?: boolean;
}
export interface TestAIRequest {
  provider?: AIProvider;
  deepseek_api_key?: string;
  openai_api_key?: string;
}
export interface TestAIResponse {
  ok: boolean;
  provider?: AIProvider | null;
  model?: string | null;
  latency_ms?: number | null;
  response_text?: string | null;
  error_type?: 'insufficient_balance' | 'auth_failed' | 'rate_limit' | 'network' | 'no_key_configured' | 'unknown' | null;
  message: string;
}

// ── AI Status ──
export interface AIStatusResponse {
  provider: AIProvider | null;
  chat_model: string;
  healthy: boolean;
  last_latency_ms: number | null;
  decisions_24h: number;
  rag_utilization_24h: number;
  rag_cases_in_db: number;
}
export interface AIDecisionItem {
  id: number;
  created_at: string;
  symbol: string;
  side: Side | null;
  execute: boolean;
  confidence: number | null;
  reasoning: string;
  top1_distance: number | null;
  rag_case_count: number;
}
export interface AIDecisionsResponse {
  decisions: AIDecisionItem[];
  count: number;
}

// ── Charts ──
export interface Kline {
  ts: number;     // ms epoch
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
export interface KlinesResponse {
  symbol: string;
  interval: Interval;
  klines: Kline[];
}
export interface SymbolEvent {
  event_type: EventType;
  side: Side;
  price: number;
  timestamp: string;
  position_id: number;
  reasoning?: string;
  rsi_15m?: number | null;
  macd_hist_15m?: number | null;
  exit_reason?: string | null;
  pnl_pct?: number | null;
}
export interface SymbolEventsResponse {
  symbol: string;
  events: SymbolEvent[];
}

// ── Manual Order ──
export interface ManualOrderPreviewRequest {
  symbol: string;
  side: Side;
  size_usdt: number;
}
export interface ManualOrderDecisionSnapshot {
  should_trade: boolean;
  side: Side | null;
  reasoning: string;
  block_reason: string | null;
}
export interface ManualOrderRagCase {
  entry_rsi_15m: number;
  entry_macd_hist_15m: number;
  outcome: OutcomeLabel;
  pnl_pct: number;
  exit_reason: string | null;
  distance: number;
}
export interface ManualOrderAiResult {
  execute: boolean;
  sl_multiplier: number;
  tp_multiplier: number;
  size_multiplier: number;
  confidence: number;
  reasoning: string;
}
export interface ManualOrderPreviewResponse {
  symbol: string;
  side: Side;
  current_price: number;
  indicators: Record<string, number>;
  decision: ManualOrderDecisionSnapshot;
  risk_plan: Record<string, number>;
  ai_result: ManualOrderAiResult;
  rag_cases: ManualOrderRagCase[];
  rag_summary: string | null;
}
export interface ManualOrderExecuteRequest {
  symbol: string;
  side: Side;
  size_usdt: number;
  sl_multiplier: number;
  tp_multiplier: number;
  size_multiplier: number;
}
export interface ManualOrderExecuteResponse {
  position_id: number;
  symbol: string;
  side: Side;
  entry_price: number;
  sl_price: number;
  tp_price: number;
  size_usdt: number;
  strategy_id: string;
}

// ── Close Position ──
export interface ClosePositionRequest {
  exit_price: number;
  exit_reason: string;
}
export interface ClosePositionResponse {
  position_id: number;
  status: 'CLOSED';
  exit_price: number;
  exit_reason: string;
}

// ── Reflection ──
export type OutcomeClass = 'WIN' | 'LOSS' | 'SCRATCH';

export interface ReflectionRecord {
  id: number;
  paper_trade_id: number;
  created_at: string;
  why_entered: string;
  what_was_expected: string;
  what_actually_happened: string;
  correction_idea: string;
  failure_mode_key: string | null;
  setup_type: string;
  outcome_class: OutcomeClass;
  realized_r: number;
  holding_minutes: number;
  confidence_at_entry: number;
  self_assessed_prediction_accuracy: number | null;
  is_in_predicted_failure_mode: boolean | null;
  ai_provider: string | null;
  ai_model: string | null;
  ai_latency_ms: number | null;
  symbol: string | null;
  side: Side | null;
  entry_price: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  pnl_pct: number | null;
  funding_z_score_at_entry: number | null;
  funding_rate_at_entry: number | null;
}

export interface ReflectionsResponse {
  status: string;
  data: ReflectionRecord[];
}

export interface FailureMode {
  key: string;
  label_zh: string;
  label_en: string;
  description: string;
  detection_rule: string | null;
  is_active: boolean;
  sample_count: number;
  avg_loss_pct: number | null;
  last_seen_at: string | null;
  seeded: boolean;
  approved_by: string | null;
}

export interface FailureTaxonomyResponse {
  status: string;
  data: FailureMode[];
}

export interface SetupPerformanceItem {
  date: string;
  setup_type: string;
  sample_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_realized_r: number;
  expectancy: number | null;
  top_failure_mode: string | null;
}

export interface SetupPerformanceResponse {
  status: string;
  data: SetupPerformanceItem[];
}

export interface SizingRecommendation {
  id: number;
  setup_type: string;
  proposed_at: string;
  current_size_multiplier: number;
  recommended_size_multiplier: number;
  confidence_score: number;
  rationale: string;
  sample_count_30d: number | null;
  sample_count_60d: number | null;
  sample_count_90d: number | null;
  kelly_f_30d: number | null;
  kelly_f_60d: number | null;
  kelly_f_90d: number | null;
  status: string;
}

export interface SizingRecommendationsResponse {
  status: string;
  data: SizingRecommendation[];
}

export interface CalibrationPoint {
  ai_model: string;
  confidence_bucket: number;
  predicted_win_rate: number;
  actual_win_rate: number;
  sample_count: number;
  calibration_multiplier: number;
}

export interface CalibrationResponse {
  status: string;
  data: CalibrationPoint[];
}

// ── Funding (V6) ──
export interface FundingZScoreItem {
  symbol: string;
  computed_at: string;
  current_funding_rate: number;
  annualized_rate_pct: number;
  mean_30d: number | null;
  std_30d: number | null;
  zscore_30d: number | null;
  sample_size_30d: number;
  is_extreme: boolean;
  extreme_direction: string | null;
}

export interface FundingStatusResponse {
  status: string;
  data: FundingZScoreItem[];
}

export interface FundingHistoryItem {
  funding_time: string;
  funding_rate: number;
  annualized_rate: number;
  source: string;
}

export interface FundingHistoryResponse {
  status: string;
  symbol: string;
  data: FundingHistoryItem[];
}

// ── WebSocket ──
export type WsEvent =
  | { type: 'position_opened'; symbol: string; side: Side; entry: number; sl: number; tp: number; size_usdt: number; position_id: number; strategy_id: string; mode: Mode }
  | { type: 'position_closed'; position_id: number; symbol: string; exit_price: number; exit_reason: string; pnl_usdt?: number; pnl_pct?: number; holding_minutes?: number }
  | { type: 'position_extended'; position_id: number; symbol: string; new_target_close_at?: string; extension_count: number }
  | { type: 'ai_health'; provider: AIProvider; chat_model: string; last_latency_ms: number | null; healthy: boolean }
  | { type: 'scoring_stalled'; seconds_since_last_score: number; last_symbol_seen: string | null }
  | { type: 'ping'; ts: number };
