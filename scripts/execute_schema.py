"""
执行数据库 Schema SQL 脚本
使用 Supabase Python 客户端执行 SQL
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from supabase import create_client, Client
    import requests
except ImportError:
    print("正在安装依赖...")
    os.system("pip install supabase requests")
    from supabase import create_client, Client
    import requests


def execute_sql_via_rest(supabase_url: str, supabase_key: str, sql: str):
    """
    通过 Supabase REST API 执行 SQL
    注意：这需要 service_role key，而不是 anon key
    """
    url = f"{supabase_url}/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }
    
    # Supabase 没有直接的 SQL 执行端点，需要使用管理 API
    # 或者通过 pg_net 扩展
    # 这里我们尝试另一种方法：使用 Supabase Management API
    
    # 实际上，Supabase 的 REST API 不支持直接执行任意 SQL
    # 我们需要使用 Supabase Management API 或者通过数据库连接
    print("⚠️  Supabase REST API 不支持直接执行 SQL")
    print("请使用以下方法之一：")
    print("1. 在 Supabase Dashboard 的 SQL Editor 中执行")
    print("2. 使用 Supabase CLI: supabase db execute")
    print("3. 使用 PostgreSQL 客户端直接连接")
    
    return False


def execute_sql_via_postgres(supabase_url: str, sql: str):
    """
    通过 PostgreSQL 连接执行 SQL
    需要从 Supabase 获取数据库连接字符串
    """
    try:
        import psycopg2
        from urllib.parse import urlparse
        
        # 从 Supabase URL 提取数据库连接信息
        # 注意：这需要数据库密码，通常存储在环境变量中
        print("⚠️  需要数据库连接字符串才能直接执行 SQL")
        print("请从 Supabase Dashboard -> Settings -> Database 获取连接字符串")
        
        return False
    except ImportError:
        print("需要安装 psycopg2: pip install psycopg2-binary")
        return False


def main():
    """主函数"""
    # 读取 SQL 文件
    sql_file = project_root / "docs" / "database_schema.sql"
    
    if not sql_file.exists():
        print(f"❌ SQL 文件不存在: {sql_file}")
        return
    
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    print("📄 已读取 SQL 文件")
    print(f"📝 SQL 内容长度: {len(sql_content)} 字符")
    
    # 尝试从环境变量获取 Supabase 配置
    supabase_url = os.getenv("SUPABASE_URL", "https://qpufonakogxhiauojbcd.supabase.co")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    
    if not supabase_key:
        print("\n" + "="*60)
        print("❌ 未找到 Supabase 密钥")
        print("\n请设置环境变量：")
        print("  - SUPABASE_URL (可选，已有默认值)")
        print("  - SUPABASE_SERVICE_ROLE_KEY 或 SUPABASE_KEY")
        print("\n或者：")
        print("1. 在 Supabase Dashboard 的 SQL Editor 中手动执行")
        print("2. 使用 Supabase CLI")
        print("="*60)
        
        # 显示 SQL 内容供用户复制
        print("\n" + "="*60)
        print("SQL 脚本内容（可复制到 Supabase SQL Editor）：")
        print("="*60)
        print(sql_content)
        print("="*60)
        return
    
    print(f"\n🔗 Supabase URL: {supabase_url}")
    print("🔑 已找到 Supabase 密钥")
    
    # 由于 Supabase REST API 不支持直接执行 SQL
    # 我们提供手动执行指南
    print("\n" + "="*60)
    print("📋 执行指南")
    print("="*60)
    print("\n由于 Supabase REST API 的安全限制，无法直接执行 SQL。")
    print("请使用以下方法之一：\n")
    
    print("方法 1: Supabase Dashboard (推荐)")
    print("  1. 访问: https://supabase.com/dashboard/project/qpufonakogxhiauojbcd")
    print("  2. 进入 SQL Editor")
    print("  3. 点击 New Query")
    print("  4. 复制下面的 SQL 内容并执行")
    
    print("\n方法 2: Supabase CLI")
    print("  supabase db execute -f docs/database_schema.sql")
    
    print("\n方法 3: PostgreSQL 客户端")
    print("  使用 psql 或 pgAdmin 直接连接数据库执行")
    
    print("\n" + "="*60)
    print("SQL 脚本内容：")
    print("="*60)
    print(sql_content)
    print("="*60)


if __name__ == "__main__":
    main()

