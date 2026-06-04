-- ============================================
-- V4.4 数据库迁移脚本
-- 添加策略路由相关字段
-- 执行日期: 2026-01-27
-- ============================================

-- ============================================
-- 1. 为 trade_scores_v43 表添加策略字段
-- ============================================

ALTER TABLE trade_scores_v43 
ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(20),
ADD COLUMN IF NOT EXISTS side VARCHAR(10),
ADD COLUMN IF NOT EXISTS strategy_score NUMERIC;

COMMENT ON COLUMN trade_scores_v43.strategy_id IS '策略ID: SNIFFER, SNIPER, VULTURE, WAIT';
COMMENT ON COLUMN trade_scores_v43.side IS '交易方向: LONG, SHORT, NONE';
COMMENT ON COLUMN trade_scores_v43.strategy_score IS '策略特定评分 (0-100)';

-- ============================================
-- 2. 为 ai_training_data 表添加策略字段
-- ============================================

ALTER TABLE ai_training_data 
ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(20),
ADD COLUMN IF NOT EXISTS side VARCHAR(10);

COMMENT ON COLUMN ai_training_data.strategy_id IS '策略ID: SNIFFER, SNIPER, VULTURE, WAIT';
COMMENT ON COLUMN ai_training_data.side IS '交易方向: LONG, SHORT, NONE';

-- ============================================
-- 3. 为 positions_v43 表添加策略字段
-- ============================================

ALTER TABLE positions_v43 
ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(20),
ADD COLUMN IF NOT EXISTS side VARCHAR(10) DEFAULT 'LONG';

COMMENT ON COLUMN positions_v43.strategy_id IS '策略ID: SNIFFER, SNIPER, VULTURE';
COMMENT ON COLUMN positions_v43.side IS '交易方向: LONG, SHORT';

-- ============================================
-- 4. 创建索引以优化查询
-- ============================================

CREATE INDEX IF NOT EXISTS idx_trade_scores_strategy ON trade_scores_v43(strategy_id);
CREATE INDEX IF NOT EXISTS idx_trade_scores_side ON trade_scores_v43(side);
CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions_v43(strategy_id);
CREATE INDEX IF NOT EXISTS idx_positions_side ON positions_v43(side);

-- ============================================
-- 5. 验证迁移结果
-- ============================================

-- 检查字段是否添加成功
SELECT 
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name IN ('trade_scores_v43', 'ai_training_data', 'positions_v43')
  AND column_name IN ('strategy_id', 'side', 'strategy_score')
ORDER BY table_name, column_name;

-- 检查索引是否创建成功
SELECT 
    tablename,
    indexname
FROM pg_indexes
WHERE tablename IN ('trade_scores_v43', 'positions_v43')
  AND indexname LIKE '%strategy%' OR indexname LIKE '%side%'
ORDER BY tablename, indexname;

