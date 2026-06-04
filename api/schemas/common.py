"""
通用 Pydantic 模型

提供泛型 ApiResponse[T] 基础模型。
"""

from typing import Generic, TypeVar, Optional, Any, Dict
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """通用 API 响应包装器"""

    status: str
    code: int
    data: T
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
