"""
验证 Supabase 连接并帮助设置数据库
"""

import requests
import json
from pathlib import Path

# Supabase 配置
import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qpufonakogxhiauojbcd.supabase.co")
# 注意：不要把任何 key 写死进仓库。请通过环境变量提供（anon/service_role）。
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def verify_connection():
    """验证 API 密钥是否有效"""
    print("🔍 正在验证 Supabase 连接...")
    
    try:
        # 测试连接：尝试访问 REST API
        url = f"{SUPABASE_URL}/rest/v1/"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("✅ API 密钥有效，成功连接到 Supabase！")
            return True
        else:
            print(f"⚠️  连接返回状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

def check_tables():
    """检查表是否已创建"""
    print("\n📊 检查数据库表...")
    
    tables_to_check = [
        "ai_training_data_v2",
        "system_settings", 
        "market_snapshot",
        "decision_log"
    ]
    
    results = {}
    
    for table in tables_to_check:
        try:
            url = f"{SUPABASE_URL}/rest/v1/{table}"
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Range": "0-0"  # 只获取一行来测试表是否存在
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                results[table] = "✅ 已存在"
            elif response.status_code == 404:
                results[table] = "❌ 不存在"
            else:
                results[table] = f"⚠️  状态码: {response.status_code}"
                
        except Exception as e:
            results[table] = f"❌ 错误: {str(e)[:50]}"
    
    print("\n表状态检查结果：")
    print("-" * 60)
    for table, status in results.items():
        print(f"  {table:30} {status}")
    print("-" * 60)
    
    # 统计
    existing = sum(1 for s in results.values() if "✅" in s)
    missing = len(results) - existing
    
    print(f"\n📈 统计: {existing}/{len(results)} 个表已创建")
    
    if missing > 0:
        print(f"⚠️  还有 {missing} 个表需要创建")
        return False
    else:
        print("✅ 所有表都已创建！")
        return True

def show_sql_instructions():
    """显示 SQL 执行说明"""
    sql_file = Path(__file__).parent.parent / "docs" / "database_schema.sql"
    
    if not sql_file.exists():
        print("❌ SQL 文件不存在")
        return
    
    print("\n" + "="*60)
    print("📋 SQL 执行指南")
    print("="*60)
    print("\n由于 Supabase 安全限制，需要通过 Dashboard 执行 SQL：")
    print("\n步骤：")
    print("1. 访问: https://supabase.com/dashboard/project/qpufonakogxhiauojbcd")
    print("2. 左侧菜单 -> SQL Editor")
    print("3. 点击 New Query")
    print("4. 复制 SQL 文件内容并执行")
    print(f"\nSQL 文件位置: {sql_file}")
    print("\n" + "="*60)

def main():
    """主函数"""
    print("="*60)
    print("🦅 Rabbit Hunter - Supabase 连接验证工具")
    print("="*60)

    if not SUPABASE_KEY:
        print("❌ 未检测到环境变量 SUPABASE_KEY，无法继续验证。")
        print("请先设置：SUPABASE_KEY=你的 Supabase anon/service_role key")
        return
    
    # 验证连接
    if not verify_connection():
        print("\n❌ 无法连接到 Supabase，请检查 API 密钥")
        return
    
    # 检查表
    all_tables_exist = check_tables()
    
    if not all_tables_exist:
        show_sql_instructions()
    else:
        print("\n🎉 数据库 Schema 已完整设置！")
        print("可以开始使用 Rabbit Hunter 了。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")

