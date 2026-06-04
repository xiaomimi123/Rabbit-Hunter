# Rabbit Hunter - Supabase 连接验证脚本
# 使用 PowerShell 验证 API 密钥并检查表状态

$SupabaseUrl = "https://qpufonakogxhiauojbcd.supabase.co"
# 注意：这里应使用 Supabase 的 anon key / service role key（用于 PostgREST 读表验证），不要把 key 写死进仓库
$SupabaseKey = $env:SUPABASE_KEY

if (-not $SupabaseKey) {
    Write-Host "❌ 未检测到环境变量 SUPABASE_KEY" -ForegroundColor Red
    Write-Host "请先在 PowerShell 里设置（示例）：" -ForegroundColor Yellow
    Write-Host "  `$env:SUPABASE_KEY='你的 Supabase anon/service_role key'" -ForegroundColor Cyan
    exit 1
}

Write-Host "=" -NoNewline
Write-Host ("=" * 59)
Write-Host "🦅 Rabbit Hunter - Supabase 连接验证" -ForegroundColor Green
Write-Host "=" -NoNewline
Write-Host ("=" * 59)

# 验证连接
Write-Host "`n🔍 正在验证 Supabase 连接..." -ForegroundColor Yellow

$headers = @{
    "apikey" = $SupabaseKey
    "Authorization" = "Bearer $SupabaseKey"
}

try {
    Invoke-RestMethod -Uri "$SupabaseUrl/rest/v1/" -Method Get -Headers $headers -TimeoutSec 10 | Out-Null
    
    Write-Host "✅ API 密钥有效，成功连接到 Supabase！" -ForegroundColor Green
    
    # 检查表
    Write-Host "`n📊 检查数据库表..." -ForegroundColor Yellow
    
    $tables = @("ai_training_data", "system_settings", "market_snapshot", "decision_log")
    $results = @{}
    
    foreach ($table in $tables) {
        try {
            $tableUrl = "$SupabaseUrl/rest/v1/$table"
            $tableHeaders = @{
                "apikey" = $SupabaseKey
                "Authorization" = "Bearer $SupabaseKey"
                "Range" = "0-0"
            }
            
            Invoke-RestMethod -Uri $tableUrl -Method Get -Headers $tableHeaders -TimeoutSec 5 -ErrorAction Stop | Out-Null
            $results[$table] = "✅ 已存在"
        }
        catch {
            if ($_.Exception.Response.StatusCode -eq 404) {
                $results[$table] = "❌ 不存在"
            }
            else {
                $results[$table] = "⚠️  错误: $($_.Exception.Message)"
            }
        }
    }
    
    Write-Host "`n表状态检查结果：" -ForegroundColor Cyan
    Write-Host ("-" * 60)
    foreach ($table in $tables) {
        $status = $results[$table]
        Write-Host "  $($table.PadRight(30)) $status"
    }
    Write-Host ("-" * 60)
    
    $existing = ($results.Values | Where-Object { $_ -like "*✅*" }).Count
    $missing = $tables.Count - $existing
    
    Write-Host "`n📈 统计: $existing/$($tables.Count) 个表已创建" -ForegroundColor Cyan
    
    if ($missing -gt 0) {
        Write-Host "⚠️  还有 $missing 个表需要创建" -ForegroundColor Yellow
        Write-Host "`n" + ("=" * 60)
        Write-Host "📋 请执行 SQL 脚本创建缺失的表：" -ForegroundColor Yellow
        Write-Host "1. 访问: https://supabase.com/dashboard/project/qpufonakogxhiauojbcd" -ForegroundColor Cyan
        Write-Host "2. 进入 SQL Editor" -ForegroundColor Cyan
        Write-Host "3. 执行 docs/database_schema.sql 中的 SQL" -ForegroundColor Cyan
        Write-Host ("=" * 60)
    }
    else {
        Write-Host "🎉 所有表都已创建！数据库 Schema 已完整设置！" -ForegroundColor Green
    }
}
catch {
    Write-Host "❌ 连接失败: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "请检查 API 密钥是否正确" -ForegroundColor Yellow
}

Write-Host "`n"

