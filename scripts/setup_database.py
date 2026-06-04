"""
直接执行 Supabase 数据库 Schema
使用 psycopg2 直接连接 PostgreSQL 数据库
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def read_sql_file():
    """读取 SQL 文件"""
    sql_file = project_root / "docs" / "database_schema.sql"
    if not sql_file.exists():
        print(f"❌ SQL 文件不存在: {sql_file}")
        return None
    
    with open(sql_file, "r", encoding="utf-8") as f:
        return f.read()

def execute_with_psycopg2():
    """使用 psycopg2 执行 SQL"""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        print("📦 正在安装 psycopg2-binary...")
        os.system("pip install psycopg2-binary")
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    
    # 从环境变量获取数据库连接信息
    # Supabase 连接格式: postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
    db_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    
    if not db_url:
        print("\n" + "="*60)
        print("❌ 未找到数据库连接字符串")
        print("\n请设置环境变量 DATABASE_URL 或 SUPABASE_DB_URL")
        print("\n获取方式：")
        print("1. 访问 Supabase Dashboard")
        print("2. Settings -> Database")
        print("3. 复制 Connection String (URI)")
        print("="*60)
        return False
    
    sql_content = read_sql_file()
    if not sql_content:
        return False
    
    try:
        print("🔗 正在连接数据库...")
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        print("📝 正在执行 SQL 脚本...")
        # 执行 SQL（psycopg2 不支持多语句执行，需要分割）
        # 但我们可以使用 execute 方法执行整个脚本
        cursor.execute(sql_content)
        
        print("✅ SQL 执行成功！")
        
        # 验证表是否创建
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
              AND table_name IN ('ai_training_data_v2', 'system_settings', 'market_snapshot', 'decision_log')
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        print(f"\n📊 已创建的表: {[t[0] for t in tables]}")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ 数据库错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        return False

def main():
    """主函数"""
    print("="*60)
    print("🚀 Rabbit Hunter 数据库 Schema 执行工具")
    print("="*60)
    
    sql_content = read_sql_file()
    if not sql_content:
        return
    
    print(f"📄 SQL 文件已读取 ({len(sql_content)} 字符)")
    
    # 尝试使用 psycopg2 执行
    if execute_with_psycopg2():
        print("\n✅ 数据库 Schema 创建完成！")
        return
    
    # 如果无法直接执行，提供手动执行指南
    print("\n" + "="*60)
    print("📋 手动执行指南")
    print("="*60)
    print("\n方法 1: Supabase Dashboard (最简单)")
    print("  1. 访问: https://supabase.com/dashboard/project/qpufonakogxhiauojbcd")
    print("  2. 左侧菜单 -> SQL Editor")
    print("  3. 点击 New Query")
    print("  4. 复制下面的 SQL 并执行")
    
    print("\n方法 2: 设置环境变量后重新运行此脚本")
    print("  export DATABASE_URL='postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres'")
    print("  python scripts/setup_database.py")
    
    print("\n" + "="*60)
    print("SQL 脚本内容：")
    print("="*60)
    print(sql_content)
    print("="*60)

if __name__ == "__main__":
    main()

