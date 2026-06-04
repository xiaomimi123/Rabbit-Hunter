"""
币安配置管理器（V4.5）

功能：
- Secret 加密存储
- 配置热加载
- 配置缓存
"""

import os
import json
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    import base64
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    print("[WARNING] cryptography 库未安装，Secret 将明文存储（不安全）")


class BinanceConfigManager:
    """
    币安配置管理器
    
    功能：
    - Secret 加密存储/解密
    - 配置热加载
    - 配置缓存
    """
    
    def __init__(self, supabase_client=None, key_file: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            supabase_client: Supabase 客户端
            key_file: 加密密钥文件路径（默认: .binance_key）
        """
        self.supabase = supabase_client
        self.key_file = key_file or os.path.join(Path(__file__).parent.parent, ".binance_key")
        self._encryption_key: Optional[bytes] = None
        self._config_cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # 缓存 5 分钟
        
        # 初始化加密密钥
        if CRYPTOGRAPHY_AVAILABLE:
            self._init_encryption_key()
    
    def _init_encryption_key(self):
        """初始化加密密钥"""
        if not CRYPTOGRAPHY_AVAILABLE:
            return
        
        # 尝试从文件读取密钥
        if os.path.exists(self.key_file):
            try:
                with open(self.key_file, 'rb') as f:
                    self._encryption_key = f.read()
            except Exception as e:
                print(f"[WARNING] 读取加密密钥失败: {e}，将生成新密钥")
                self._generate_key()
        else:
            # 生成新密钥
            self._generate_key()
    
    def _generate_key(self):
        """生成新的加密密钥"""
        if not CRYPTOGRAPHY_AVAILABLE:
            return
        
        try:
            # 使用环境变量或系统信息作为盐值
            salt = os.environ.get("BINANCE_ENCRYPTION_SALT", "rabbit_hunter_v45").encode()
            
            # 生成密钥
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend()
            )
            key = base64.urlsafe_b64encode(kdf.derive(b"rabbit_hunter_binance_secret"))
            self._encryption_key = key  # 保存原始密钥（bytes）
            
            # 保存密钥到文件
            try:
                with open(self.key_file, 'wb') as f:
                    f.write(key)
                # 设置文件权限（仅所有者可读）
                os.chmod(self.key_file, 0o600)
            except Exception as e:
                print(f"[WARNING] 保存加密密钥失败: {e}")
        except Exception as e:
            print(f"[ERROR] 生成加密密钥失败: {e}")
            self._encryption_key = None
    
    def encrypt_secret(self, secret: str) -> str:
        """
        加密 Secret
        
        Args:
            secret: 原始 Secret
            
        Returns:
            加密后的 Secret（Base64 编码）
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self._encryption_key:
            # 如果加密不可用，返回原始值（不安全，但向后兼容）
            print("[WARNING] 加密不可用，Secret 将明文存储")
            return secret
        
        try:
            if isinstance(self._encryption_key, bytes):
                fernet = Fernet(self._encryption_key)
            else:
                fernet = self._encryption_key
            
            encrypted = fernet.encrypt(secret.encode())
            return encrypted.decode()
        except Exception as e:
            print(f"[ERROR] 加密 Secret 失败: {e}")
            return secret  # 失败时返回原始值
    
    def decrypt_secret(self, encrypted_secret: str) -> str:
        """
        解密 Secret
        
        Args:
            encrypted_secret: 加密后的 Secret
            
        Returns:
            解密后的 Secret
        """
        if not CRYPTOGRAPHY_AVAILABLE or not self._encryption_key:
            # 如果加密不可用，假设是明文
            return encrypted_secret
        
        try:
            if isinstance(self._encryption_key, bytes):
                fernet = Fernet(self._encryption_key)
            else:
                fernet = self._encryption_key
            
            decrypted = fernet.decrypt(encrypted_secret.encode())
            return decrypted.decode()
        except Exception as e:
            # 如果解密失败，可能是旧数据（明文），直接返回
            print(f"[WARNING] 解密 Secret 失败（可能是明文）: {e}")
            return encrypted_secret
    
    def get_config(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取币安配置（带缓存）
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            配置字典，如果未配置返回 None
        """
        # 检查缓存
        if not force_refresh and self._config_cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_ttl:
                return self._config_cache
        
        if not self.supabase:
            return None
        
        try:
            # 从数据库读取配置
            api_key_response = self.supabase.table("system_settings").select("value").eq("key", "binance_api_key").execute()
            api_secret_response = self.supabase.table("system_settings").select("value").eq("key", "binance_api_secret").execute()
            testnet_response = self.supabase.table("system_settings").select("value").eq("key", "binance_testnet").execute()
            leverage_response = self.supabase.table("system_settings").select("value").eq("key", "binance_leverage").execute()
            
            api_key = api_key_response.data[0].get("value") if api_key_response.data else None
            api_secret_encrypted = api_secret_response.data[0].get("value") if api_secret_response.data else None
            testnet = testnet_response.data[0].get("value", "false").lower() in ("true", "1") if testnet_response.data else False
            leverage = int(leverage_response.data[0].get("value", "10")) if leverage_response.data and leverage_response.data[0].get("value") else 10
            
            if not api_key or not api_secret_encrypted:
                self._config_cache = None
                return None
            
            # 解密 Secret
            api_secret = self.decrypt_secret(api_secret_encrypted)
            
            # 验证解密后的 Secret 长度（币安 Secret 应该是 64 字符）
            # 如果解密失败，decrypt_secret 会返回加密后的值（长度 > 100）
            if api_secret and len(api_secret) != 64:
                if len(api_secret) > 100:
                    # 解密失败，Secret 仍然是加密状态
                    print(f"[ERROR] Secret 解密失败！")
                    print(f"[ERROR] 解密后的 Secret 长度: {len(api_secret)} 字符（应该是 64）")
                    print(f"[ERROR] 加密前的 Secret 长度: {len(api_secret_encrypted)} 字符")
                    print(f"[ERROR] 这会导致 API 调用失败（-2008 错误）")
                    print(f"[ERROR] 请在前端重新保存一次配置，或检查 .binance_key 文件")
                    # 不抛出异常，让调用者知道配置有问题
                elif len(api_secret_encrypted) == 64:
                    # 可能是旧数据（未加密），直接使用
                    print(f"[INFO] Secret 未加密（64 字符），直接使用")
                    api_secret = api_secret_encrypted
                else:
                    print(f"[WARNING] Secret 长度异常: {len(api_secret)} 字符")
            
            config = {
                "api_key": api_key,
                "api_secret": api_secret,
                "testnet": testnet,
                "leverage": leverage,
            }
            
            # 更新缓存
            self._config_cache = config
            self._cache_time = datetime.now()
            
            return config
        except Exception as e:
            print(f"[ERROR] 获取币安配置失败: {e}")
            return None
    
    def save_config(self, api_key: str, api_secret: str, testnet: bool = False, leverage: int = 10) -> bool:
        """
        保存币安配置（加密 Secret）
        
        Args:
            api_key: API Key
            api_secret: API Secret（将加密存储）
            testnet: 是否使用测试网
            leverage: 杠杆倍数（默认 10）
            
        Returns:
            是否保存成功
        """
        if not self.supabase:
            return False
        
        try:
            # 加密 Secret
            encrypted_secret = self.encrypt_secret(api_secret)
            
            # 保存到数据库
            upsert_data = [
                {
                    "key": "binance_api_key",
                    "value": api_key,
                    "updated_at": datetime.now().isoformat(),
                },
                {
                    "key": "binance_api_secret",
                    "value": encrypted_secret,  # 加密后的 Secret
                    "updated_at": datetime.now().isoformat(),
                },
                {
                    "key": "binance_testnet",
                    "value": "true" if testnet else "false",
                    "updated_at": datetime.now().isoformat(),
                },
                {
                    "key": "binance_leverage",
                    "value": str(leverage),
                    "updated_at": datetime.now().isoformat(),
                },
            ]
            
            for item in upsert_data:
                self.supabase.table("system_settings").upsert(
                    item,
                    on_conflict="key"
                ).execute()
            
            # 清除缓存，强制下次重新加载
            self._config_cache = None
            self._cache_time = None
            
            # ⚠️ 注意：不更新环境变量，避免覆盖数据采集器的配置
            # 环境变量 (BINANCE_API_KEY) 用于数据采集器（只读数据）
            # 数据库配置用于交易系统（需要交易权限）
            # 两者可以不同：实盘数据采集 + 测试网交易
            
            print("[INFO] ✅ 币安配置已保存到数据库（Secret 已加密）")
            print("[INFO] 💡 提示：环境变量中的 BINANCE_API_KEY 保持不变（用于数据采集器）")
            return True
        except Exception as e:
            print(f"[ERROR] 保存币安配置失败: {e}")
            return False
    
    def delete_config(self) -> bool:
        """删除币安配置"""
        if not self.supabase:
            return False
        
        try:
            self.supabase.table("system_settings").delete().eq("key", "binance_api_key").execute()
            self.supabase.table("system_settings").delete().eq("key", "binance_api_secret").execute()
            self.supabase.table("system_settings").delete().eq("key", "binance_testnet").execute()
            self.supabase.table("system_settings").delete().eq("key", "binance_leverage").execute()
            
            # 清除缓存
            self._config_cache = None
            self._cache_time = None
            
            # 清除环境变量
            os.environ.pop("BINANCE_API_KEY", None)
            os.environ.pop("BINANCE_API_SECRET", None)
            os.environ.pop("BINANCE_TESTNET", None)
            os.environ.pop("BINANCE_LEVERAGE", None)
            
            print("[INFO] ✅ 币安配置已删除")
            return True
        except Exception as e:
            print(f"[ERROR] 删除币安配置失败: {e}")
            return False
    
    def is_configured(self) -> bool:
        """检查是否已配置"""
        config = self.get_config()
        return config is not None


# 全局配置管理器实例（单例模式）
_config_manager: Optional[BinanceConfigManager] = None


def get_config_manager(supabase_client=None) -> BinanceConfigManager:
    """
    获取配置管理器实例（单例）
    
    Args:
        supabase_client: Supabase 客户端
        
    Returns:
        配置管理器实例
    """
    global _config_manager
    
    if _config_manager is None:
        _config_manager = BinanceConfigManager(supabase_client=supabase_client)
    elif supabase_client and _config_manager.supabase != supabase_client:
        # 如果提供了新的客户端，更新它
        _config_manager.supabase = supabase_client
    
    return _config_manager


__all__ = ["BinanceConfigManager", "get_config_manager"]

