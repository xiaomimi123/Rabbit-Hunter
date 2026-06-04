-- ============================================
-- V4.4 策略验证 SQL 查询脚本
-- 目标：验证 Sniffer 和 Vulture 策略的有效性
-- 日期：2026-01-27
-- ============================================

-- ============================================
-- 1. Sniffer 策略候选币（P2 + 爆量 + OI 上升）
-- ============================================

-- 查找过去 3 天符合 Sniffer 条件的币种
WITH sniffer_candidates AS (
    SELECT 
        symbol,
        created_at,
        features->>'phase' as phase,
        (features->>'volume_spike')::float as volume_spike,
        (features->>'oi_change')::float as oi_change,
        (features->>'oi_change_1h')::float as oi_change_1h,
        sentiment_score,
        structure_score,
        final_score,
        features->>'funding_rate' as funding_rate,
        features->>'ls_ratio' as ls_ratio
    FROM trade_scores_v43
    WHERE features->>'phase' = 'P2_ACCUMULATION'
      AND (features->>'volume_spike')::float > 3.0
      AND (
          (features->>'oi_change')::float > 0.05 
          OR (features->>'oi_change_1h')::float > 0.05
      )
      AND created_at >= NOW() - INTERVAL '3 days'
    ORDER BY created_at DESC
)
SELECT 
    symbol,
    created_at,
    phase,
    volume_spike,
    oi_change,
    oi_change_1h,
    sentiment_score,
    structure_score,
    final_score,
    funding_rate,
    ls_ratio
FROM sniffer_candidates
LIMIT 50;

-- ============================================
-- 2. Vulture 策略候选币（P3B/P4 + 被拒 + OI 下降）
-- ============================================

-- 查找过去 3 天符合 Vulture 条件的币种
WITH vulture_candidates AS (
    SELECT 
        symbol,
        created_at,
        features->>'phase' as phase,
        decision_policy->>'block_reason' as block_reason,
        (features->>'oi_change')::float as oi_change,
        (features->>'oi_change_1h')::float as oi_change_1h,
        structure_score,
        final_score,
        features->>'funding_rate' as funding_rate,
        features->>'ls_ratio' as ls_ratio
    FROM trade_scores_v43
    WHERE features->>'phase' IN ('P3B_PUMP_LATE', 'P4_DISTRIBUTION')
      AND (
          decision_policy->>'block_reason' = 'LOW_EXPECTED_RETURN'
          OR decision_policy->>'block_reason' LIKE '%LOW_EXPECTED%'
      )
      AND (
          (features->>'oi_change')::float < -0.05 
          OR (features->>'oi_change_1h')::float < -0.05
      )
      AND created_at >= NOW() - INTERVAL '3 days'
    ORDER BY created_at DESC
)
SELECT 
    symbol,
    created_at,
    phase,
    block_reason,
    oi_change,
    oi_change_1h,
    structure_score,
    final_score,
    funding_rate,
    ls_ratio
FROM vulture_candidates
LIMIT 50;

-- ============================================
-- 3. 统计信息
-- ============================================

-- Sniffer 候选币统计
SELECT 
    'Sniffer 候选币' as strategy,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(*) as total_records,
    AVG((features->>'volume_spike')::float) as avg_volume_spike,
    AVG((features->>'oi_change')::float) as avg_oi_change,
    AVG(sentiment_score) as avg_sentiment_score,
    AVG(final_score) as avg_final_score
FROM trade_scores_v43
WHERE features->>'phase' = 'P2_ACCUMULATION'
  AND (features->>'volume_spike')::float > 3.0
  AND (
      (features->>'oi_change')::float > 0.05 
      OR (features->>'oi_change_1h')::float > 0.05
  )
  AND created_at >= NOW() - INTERVAL '3 days';

-- Vulture 候选币统计
SELECT 
    'Vulture 候选币' as strategy,
    COUNT(DISTINCT symbol) as unique_symbols,
    COUNT(*) as total_records,
    AVG((features->>'oi_change')::float) as avg_oi_change,
    AVG(structure_score) as avg_structure_score,
    AVG(final_score) as avg_final_score
FROM trade_scores_v43
WHERE features->>'phase' IN ('P3B_PUMP_LATE', 'P4_DISTRIBUTION')
  AND (
      decision_policy->>'block_reason' = 'LOW_EXPECTED_RETURN'
      OR decision_policy->>'block_reason' LIKE '%LOW_EXPECTED%'
  )
  AND (
      (features->>'oi_change')::float < -0.05 
      OR (features->>'oi_change_1h')::float < -0.05
  )
  AND created_at >= NOW() - INTERVAL '3 days';

-- ============================================
-- 4. 阶段分布统计（过去 3 天）
-- ============================================

SELECT 
    features->>'phase' as phase,
    COUNT(*) as count,
    COUNT(DISTINCT symbol) as unique_symbols,
    AVG(final_score) as avg_score
FROM trade_scores_v43
WHERE created_at >= NOW() - INTERVAL '3 days'
GROUP BY features->>'phase'
ORDER BY count DESC;

