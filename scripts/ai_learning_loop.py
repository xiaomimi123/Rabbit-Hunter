"""
AI 自动学习循环（Rabbit Hunter V4.2）

功能：
- 在后台持续运行，定期自动触发 AI 参数调优
- 不需要手动运行，系统自动优化
- 记录学习历史，持续改进
"""

import os
import sys
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client

# 添加项目根目录到路径（用于导入其他模块）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加 scripts 目录到路径（用于相对导入）
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# 导入 ai_auto_tuner（支持多种导入方式）
try:
    # 先尝试相对导入（因为 ai_learning_loop.py 在 scripts/ 目录下）
    from ai_auto_tuner import run_auto_tuning_with_verification
except ImportError:
    try:
        # 再尝试绝对导入
        from scripts.ai_auto_tuner import run_auto_tuning_with_verification
    except ImportError:
        # 最后尝试从项目根目录导入
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ai_auto_tuner",
            os.path.join(_scripts_dir, "ai_auto_tuner.py")
        )
        if spec and spec.loader:
            ai_auto_tuner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ai_auto_tuner)
            run_auto_tuning_with_verification = ai_auto_tuner.run_auto_tuning_with_verification
        else:
            raise ImportError("无法导入 ai_auto_tuner 模块")

load_dotenv()


class AILearningLoop:
    """AI 自动学习循环"""
    
    def __init__(
        self,
        tuning_interval_hours: int = 6,  # 每 6 小时调优一次
        min_data_points: int = 100,      # 最少需要 100 个数据点
        min_trades: int = 10,            # 最少需要 10 笔交易
    ):
        """
        初始化学习循环
        
        Args:
            tuning_interval_hours: 调优间隔（小时）
            min_data_points: 最少需要的数据点数量
            min_trades: 最少需要的交易数量
        """
        self.tuning_interval_hours = tuning_interval_hours
        self.min_data_points = min_data_points
        self.min_trades = min_trades
        
        # 初始化 Supabase
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("未配置 Supabase URL 或 Key")
        
        self.supabase = create_client(supabase_url, supabase_key)
        
        # 上次调优时间
        self.last_tuning_time: Optional[datetime] = None
        
        # 运行状态
        self.is_running = False
    
    def check_data_availability(self) -> tuple[bool, str]:
        """
        检查是否有足够的数据进行调优
        
        Returns:
            (是否有足够数据, 原因)
        """
        try:
            # 检查最近 7 天的数据点
            start_time = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            data_response = (
                self.supabase.table("ai_training_data")
                .select("id", count="exact")
                .gte("created_at", start_time)
                .not_.is_("ai_score", "null")
                .execute()
            )
            
            data_count = data_response.count if hasattr(data_response, 'count') else len(data_response.data or [])
            
            # 检查最近 7 天的交易
            trade_response = (
                self.supabase.table("paper_trades")
                .select("id", count="exact")
                .gte("created_at", start_time)
                .execute()
            )
            
            trade_count = trade_response.count if hasattr(trade_response, 'count') else len(trade_response.data or [])
            
            if data_count < self.min_data_points:
                return False, f"数据点不足（需要 {self.min_data_points}，实际 {data_count}）"
            
            if trade_count < self.min_trades:
                return False, f"交易数量不足（需要 {self.min_trades}，实际 {trade_count}）"
            
            return True, f"数据充足（数据点: {data_count}, 交易: {trade_count}）"
            
        except Exception as e:
            return False, f"检查数据失败: {e}"
    
    def should_run_tuning(self) -> bool:
        """
        判断是否应该运行调优
        
        Returns:
            是否应该运行
        """
        # 如果从未运行过，立即运行
        if self.last_tuning_time is None:
            return True
        
        # 检查是否到了调优时间
        time_since_last = datetime.now(timezone.utc) - self.last_tuning_time
        if time_since_last >= timedelta(hours=self.tuning_interval_hours):
            return True
        
        return False
    
    async def run_tuning(self) -> dict:
        """
        运行一次调优
        
        Returns:
            调优结果
        """
        print(f"\n{'='*60}")
        print(f"🤖 [AI 学习循环] 开始自动调优 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")
        
        # 检查数据可用性
        has_data, reason = self.check_data_availability()
        if not has_data:
            print(f"⏸️  [AI 学习循环] 跳过调优: {reason}")
            return {
                "success": False,
                "reason": reason,
                "skipped": True,
            }
        
        print(f"✅ [AI 学习循环] {reason}")
        
        try:
            # 运行调优（使用 Time Machine 验证）
            result = run_auto_tuning_with_verification(
                self.supabase,
                config_path="strategy_config.json",
                verification_method="time_machine",
                min_improvement_pct=1.0,  # 至少改进 1%
            )
            
            # 更新上次调优时间
            self.last_tuning_time = datetime.now(timezone.utc)
            
            if result.get("success"):
                if result.get("should_apply"):
                    print(f"✅ [AI 学习循环] 调优完成，新配置已应用")
                else:
                    print(f"⚠️  [AI 学习循环] 调优完成，但新配置未达到改进阈值")
            else:
                print(f"❌ [AI 学习循环] 调优失败: {result.get('reason', '未知错误')}")
            
            return result
            
        except Exception as e:
            print(f"❌ [AI 学习循环] 调优异常: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "reason": str(e),
            }
    
    async def run_loop(self):
        """
        运行学习循环（持续运行）
        """
        self.is_running = True
        print(f"🚀 [AI 学习循环] 启动自动学习循环（每 {self.tuning_interval_hours} 小时调优一次）")
        
        # 首次运行（如果数据充足）
        if self.should_run_tuning():
            await self.run_tuning()
        
        # 持续循环
        while self.is_running:
            try:
                # 等待到下次调优时间
                await asyncio.sleep(60)  # 每分钟检查一次
                
                if self.should_run_tuning():
                    await self.run_tuning()
                    
            except KeyboardInterrupt:
                print("\n⏹️  [AI 学习循环] 收到停止信号，正在退出...")
                self.is_running = False
                break
            except Exception as e:
                print(f"❌ [AI 学习循环] 循环异常: {e}")
                await asyncio.sleep(60)  # 出错后等待 1 分钟再继续
    
    def stop(self):
        """停止学习循环"""
        self.is_running = False
        print("⏹️  [AI 学习循环] 已停止")


async def main():
    """主函数：启动学习循环"""
    # 从环境变量读取配置
    tuning_interval = int(os.environ.get("AI_LEARNING_INTERVAL_HOURS", "6"))
    min_data_points = int(os.environ.get("AI_LEARNING_MIN_DATA_POINTS", "100"))
    min_trades = int(os.environ.get("AI_LEARNING_MIN_TRADES", "10"))
    
    loop = AILearningLoop(
        tuning_interval_hours=tuning_interval,
        min_data_points=min_data_points,
        min_trades=min_trades,
    )
    
    try:
        await loop.run_loop()
    except KeyboardInterrupt:
        loop.stop()


if __name__ == "__main__":
    asyncio.run(main())

