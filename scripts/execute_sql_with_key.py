"""
使用 Supabase API 密钥执行 SQL
"""

import os
import sys
import requests
from pathlib import Path

# 项目根目录
project_root = Path(__file__).parent.parent

# Supabase 配置
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://qpufonakogxhiauojbcd.supabase.co")
# 注意：不要把任何 key 写死进仓库。请通过环境变量提供（anon/service_role/pat 取决于用途）。
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

def read_sql_file():
    """读取 SQL 文件"""
    sql_file = project_root / "docs" / "database_schema.sql"
    if not sql_file.exists():
        print(f"❌ SQL 文件不存在: {sql_file}")
        return None
    
    with open(sql_file, "r", encoding="utf-8") as f:
        return f.read()

def execute_via_management_api(sql_content):
    """
    尝试通过 Supabase Management API 执行 SQL
    注意：Management API 需要 project API key
    """
    print("🔗 正在连接 Supabase...")
    
    # Supabase Management API 端点（如果可用）
    # 实际上 Supabase 没有公开的 SQL 执行 API
    # 我们需要使用其他方法
    
    print("⚠️  Supabase REST API 不支持直接执行 SQL（安全限制）")
    print("正在尝试其他方法...")
    return False

def execute_via_postgrest_rpc(sql_content):
    """
    尝试通过 PostgREST RPC 执行 SQL
    需要先创建一个函数
    """
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    # 这需要先在数据库中创建一个 exec_sql 函数
    # 但为了安全，Supabase 通常不允许这样做
    print("⚠️  此方法需要数据库函数支持")
    return False

def create_exec_sql_function():
    """
    尝试创建一个执行 SQL 的函数
    但这通常需要 service_role key 和特殊权限
    """
    # 创建函数的 SQL
    create_function_sql = """
    CREATE OR REPLACE FUNCTION exec_sql(sql_text text)
    RETURNS void
    LANGUAGE plpgsql
    SECURITY DEFINER
    AS $$
    BEGIN
        EXECUTE sql_text;
    END;
    $$;
    """
    
    print("📝 尝试创建 exec_sql 函数...")
    # 这需要通过数据库直接连接，不能通过 REST API
    return False

def execute_via_supabase_client():
    """
    使用 Supabase Python 客户端
    但客户端也不支持直接执行 SQL
    """
    try:
        from supabase import create_client
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Supabase 客户端主要用于 CRUD 操作，不支持执行 SQL
        print("⚠️  Supabase Python 客户端不支持直接执行 SQL")
        return False
        
    except ImportError:
        print("📦 正在安装 supabase 库...")
        os.system("pip install supabase")
        return False
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False

def main():
    """主函数"""
    print("="*60)
    print("🚀 Rabbit Hunter - 使用 API 密钥执行 SQL")
    print("="*60)
    
    sql_content = read_sql_file()
    if not sql_content:
        return
    
    print(f"📄 SQL 文件已读取 ({len(sql_content)} 字符)")
    if not SUPABASE_KEY:
        print("❌ 未检测到环境变量 SUPABASE_KEY，无法继续。")
        return

    print(f"🔗 Supabase URL: {SUPABASE_URL}")
    print(f"🔑 API Key: {SUPABASE_KEY[:12]}...（已从环境变量读取）")
    
    # 尝试各种方法
    methods = [
        ("Supabase Management API", execute_via_management_api),
        ("PostgREST RPC", execute_via_postgrest_rpc),
        ("Supabase Python Client", execute_via_supabase_client),
    ]
    
    success = False
    for method_name, method_func in methods:
        print(f"\n尝试方法: {method_name}")
        try:
            if method_func(sql_content):
                success = True
                break
        except Exception as e:
            print(f"❌ {method_name} 失败: {e}")
    
    if not success:
        print("\n" + "="*60)
        print("📋 由于 Supabase 安全限制，无法通过 API 直接执行 SQL")
        print("="*60)
        print("\n✅ 推荐方法：使用 Supabase Dashboard")
        print("\n步骤：")
        print("1. 访问: https://supabase.com/dashboard/project/qpufonakogxhiauojbcd")
        print("2. 进入 SQL Editor")
        print("3. 点击 New Query")
        print("4. 复制下面的 SQL 并执行")
        
        print("\n" + "="*60)
        print("SQL 脚本内容：")
        print("="*60)
        print(sql_content)
        print("="*60)
        
        # 尝试使用 API 密钥验证连接
        print("\n🔍 验证 API 密钥连接...")
        try:
            # 测试连接：查询一个简单的表
            test_url = f"{SUPABASE_URL}/rest/v1/"
            headers = {
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            }
            
            response = requests.get(test_url, headers=headers, timeout=5)
            if response.status_code == 200:
                print("✅ API 密钥有效，可以连接 Supabase")
                print("💡 虽然无法直接执行 SQL，但可以：")
                print("   - 读取/写入数据表")
                print("   - 使用 Supabase Dashboard 执行 SQL")
            else:
                print(f"⚠️  API 连接测试返回: {response.status_code}")
        except Exception as e:
            print(f"⚠️  连接测试失败: {e}")

if __name__ == "__main__":
    main()

