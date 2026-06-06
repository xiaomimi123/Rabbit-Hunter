-- v45 临时止血迁移
-- 目的：为 SHORT 持仓增加 lowest_price 列（与 LONG 的 highest_price 对称），
--      为后续端到端修复 chandelier_stop 的 SHORT 数学做铺垫。
--
-- 本次发布默认禁用 SHORT 入场（ENABLE_SHORT_TRADING=false）。
-- 已有 OPEN SHORT 仓位继续按旧逻辑管理；新仓位会被在 strategy_router 和
-- position_manager 两层拦截。
--
-- 应用方法（Supabase）：
--   1. 在 Supabase Dashboard → SQL Editor 粘贴并执行
--   2. 或 psql 链接到数据库后 \i v45_short_kill_switch_migration.sql
--
-- 幂等：可以重复运行；ALTER 失败（列已存在）会被忽略。

ALTER TABLE positions_v43 ADD COLUMN IF NOT EXISTS lowest_price  DOUBLE PRECISION;
ALTER TABLE positions_v43 ADD COLUMN IF NOT EXISTS highest_price DOUBLE PRECISION;

COMMENT ON COLUMN positions_v43.highest_price IS 'LONG 持仓自开仓以来的最高价；trailing chandelier stop 的参考点';
COMMENT ON COLUMN positions_v43.lowest_price  IS 'SHORT 持仓自开仓以来的最低价；trailing chandelier stop 的参考点（v45 新增）';
