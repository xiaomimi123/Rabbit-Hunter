# Rabbit Hunter - 使用 Supabase PAT 执行 Schema 并验证
# 说明：
# - 优先从环境变量 SUPABASE_PAT 读取 token
# - 若当前会话读不到，则从 Cursor 终端记录文件中提取（避免在命令里明文写 token）

param(
  [string]$ProjectRef = "qpufonakogxhiauojbcd",
  [string]$SqlFile = (Join-Path (Resolve-Path "E:\cursor*\Rabbit Hunter").Path "docs\database_schema.sql"),
  [string]$TokenEnvVar = "SUPABASE_PAT",
  [string]$TokenFallbackFile = "c:\Users\Administrator\.cursor\projects\e-cursor-Rabbit-Hunter\terminals\1.txt",
  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

function Get-PatToken {
  param([string]$EnvVar, [string]$FallbackFile)

  $t = [Environment]::GetEnvironmentVariable($EnvVar, "Process")
  if ($t) { return $t }

  if (-not (Test-Path -LiteralPath $FallbackFile)) {
    throw "未找到 token：环境变量 $EnvVar 为空，且 fallback 文件不存在：$FallbackFile"
  }

  $content = Get-Content -LiteralPath $FallbackFile -Raw
  $m = [regex]::Match($content, "sbp_[a-zA-Z0-9]+")
  if (-not $m.Success) {
    throw "未在 fallback 文件中找到 sbp_ token：$FallbackFile"
  }
  return $m.Value
}

function Invoke-DbQuery {
  param([string]$ProjectRef, [string]$Token, [string]$Query)

  $uri = "https://api.supabase.com/v1/projects/$ProjectRef/database/query"
  $headers = @{
    Authorization = "Bearer $Token"
    "Content-Type" = "application/json"
    Accept = "application/json"
  }
  $body = @{ query = $Query } | ConvertTo-Json -Depth 10

  return Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body -TimeoutSec 180
}

Write-Host "🧩 准备执行 Supabase schema..." -ForegroundColor Cyan
Write-Host " - ProjectRef: $ProjectRef"
Write-Host " - SqlFile: $SqlFile"

if (-not (Test-Path -LiteralPath $SqlFile)) {
  throw "SQL 文件不存在：$SqlFile"
}

$token = Get-PatToken -EnvVar $TokenEnvVar -FallbackFile $TokenFallbackFile
Write-Host "🔐 PAT 已获取（已隐藏）" -ForegroundColor Green

$schemaSql = Get-Content -LiteralPath $SqlFile -Raw

Write-Host "🚀 执行 schema..." -ForegroundColor Yellow
$resp = Invoke-DbQuery -ProjectRef $ProjectRef -Token $token -Query $schemaSql
Write-Host "✅ schema 执行完成" -ForegroundColor Green

if (-not $SkipVerify) {
  Write-Host "🔎 开始验证表/枚举..." -ForegroundColor Yellow
  $verifySql = @"
select
  (select count(*) from information_schema.tables where table_schema='public' and table_name='ai_training_data') as has_ai_training_data,
  (select count(*) from information_schema.tables where table_schema='public' and table_name='system_settings') as has_system_settings,
  (select count(*) from information_schema.tables where table_schema='public' and table_name='market_snapshot') as has_market_snapshot,
  (select count(*) from information_schema.tables where table_schema='public' and table_name='decision_log') as has_decision_log,
  (select count(*) from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typname='market_regime_type') as has_market_regime_type,
  (select count(*) from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typname='phase_type') as has_phase_type
;
select key, value from system_settings order by key limit 20;
"@

  $v = Invoke-DbQuery -ProjectRef $ProjectRef -Token $token -Query $verifySql
  Write-Host "✅ 验证查询已返回（已输出 JSON）" -ForegroundColor Green
  $v | ConvertTo-Json -Depth 20
}



