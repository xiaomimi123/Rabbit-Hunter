"""
V4.4 数据库迁移脚本执行器

执行 SQL 迁移脚本，添加策略路由相关字段
"""

import os
import sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

load_dotenv()

try:
    from supabase import create_client, Client
except ImportError:
    print("[ERROR] 未安装 supabase 库，请运行: pip install supabase")
    sys.exit(1)

def execute_migration():
    """执行数据库迁移"""
    print("=" * 80)
    print("V4.4 数据库迁移")
    print("=" * 80)
    print()
    
    # 读取 Supabase 配置
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        print("[ERROR] 未配置 Supabase 环境变量")
        print("  需要: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (或 SUPABASE_KEY)")
        sys.exit(1)
    
    # 创建 Supabase 客户端
    supabase: Client = create_client(supabase_url, supabase_key)
    
    # 读取 SQL 文件
    sql_file = os.path.join(BASE_DIR, "scripts", "v44_database_migration.sql")
    if not os.path.exists(sql_file):
        print(f"[ERROR] SQL 文件不存在: {sql_file}")
        sys.exit(1)
    
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    # 分割 SQL 语句（按分号分割，但保留注释）
    sql_statements = []
    current_statement = ""
    for line in sql_content.split("\n"):
        stripped = line.strip()
        # 跳过注释和空行
        if stripped.startswith("--") or not stripped:
            continue
        current_statement += line + "\n"
        if stripped.endswith(";"):
            sql_statements.append(current_statement.strip())
            current_statement = ""
    
    if current_statement.strip():
        sql_statements.append(current_statement.strip())
    
    print(f"[INFO] 找到 {len(sql_statements)} 条 SQL 语句")
    print()
    
    # 执行每条 SQL 语句
    success_count = 0
    error_count = 0
    
    for i, sql in enumerate(sql_statements, 1):
        if not sql.strip():
            continue
        
        print(f"[{i}/{len(sql_statements)}] 执行 SQL...")
        try:
            # Supabase Python 客户端不支持直接执行 SQL
            # 需要使用 RPC 或 REST API
            # 这里我们使用 Supabase 的 REST API 执行 SQL
            import requests
            
            response = requests.post(
                f"{supabase_url}/rest/v1/rpc/exec_sql",
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                },
                json={"query": sql},
                timeout=30,
            )
            
            if response.status_code == 200:
                print(f"  ✅ 成功")
                success_count += 1
            else:
                print(f"  ⚠️  状态码: {response.status_code}")
                print(f"  响应: {response.text[:200]}")
                # 某些操作（如 CREATE INDEX IF NOT EXISTS）可能返回错误但实际成功
                if "already exists" in response.text.lower() or "duplicate" in response.text.lower():
                    print(f"  ✅ 已存在，跳过")
                    success_count += 1
                else:
                    error_count += 1
        except Exception as e:
            print(f"  ❌ 错误: {type(e).__name__}: {e}")
            error_count += 1
        
        print()
    
    # 验证迁移结果
    print("=" * 80)
    print("验证迁移结果")
    print("=" * 80)
    print()
    
    try:
        # 检查 trade_scores_v43 表
        result = supabase.table("trade_scores_v43").select("strategy_id, side, strategy_score").limit(1).execute()
        print("✅ trade_scores_v43 表字段检查通过")
    except Exception as e:
        print(f"⚠️  trade_scores_v43 表字段检查失败: {e}")
    
    try:
        # 检查 positions_v43 表
        result = supabase.table("positions_v43").select("strategy_id, side").limit(1).execute()
        print("✅ positions_v43 表字段检查通过")
    except Exception as e:
        print(f"⚠️  positions_v43 表字段检查失败: {e}")
    
    print()
    print("=" * 80)
    print(f"迁移完成: {success_count} 成功, {error_count} 失败")
    print("=" * 80)
    
    if error_count > 0:
        print()
        print("⚠️  部分 SQL 语句执行失败")
        print("   请手动检查数据库，或使用 Supabase Dashboard 执行 SQL 脚本")
        print(f"   SQL 文件位置: {sql_file}")
        sys.exit(1)

if __name__ == "__main__":
    execute_migration()

