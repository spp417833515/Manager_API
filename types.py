#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
类型定义模块
定义框架中使用的所有类型
"""

from typing import Dict, Any, Optional, List, Union, Callable, TypedDict
from dataclasses import dataclass
from enum import Enum


class HTTPMethod(str, Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    WS = "WS"  # WebSocket


class CallbackData(TypedDict, total=False):
    """回调函数接收的数据结构"""
    type: str           # HTTP方法
    path: str           # 请求路径
    method: str         # 同type，为了兼容性
    params: Dict[str, Any]      # 路径参数
    query: Dict[str, Any]       # 查询参数
    body: Any          # 请求体
    headers: Dict[str, str]     # 请求头
    cookies: Dict[str, str]     # Cookies
    client: str        # 客户端IP
    request_id: str    # 请求ID
    timestamp: float   # 请求时间戳
    files: List[Any]   # 上传的文件
    route_info: Dict[str, Any]  # 路由信息


@dataclass
class RouteInfo:
    """路由信息"""
    method: str
    path: str
    group: str = "default"
    name: str = ""
    cache: Optional[bool] = None
    ratelimit: Optional[Dict[str, int]] = None
    auth: bool = False
    options: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.options is None:
            self.options = {}


@dataclass
class ResponseData:
    """响应数据结构"""
    status: int = 200
    data: Any = None
    headers: Optional[Dict[str, str]] = None
    cookies: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.headers:
            result["headers"] = self.headers
        if self.cookies:
            result["cookies"] = self.cookies
        return result


# 响应类型
ResponseType = Union[
    dict,           # 自动转JSON
    str,            # 文本响应
    bytes,          # 二进制响应
    None,           # 204 No Content
    ResponseData,   # 完整响应控制
]


# 回调函数类型
CallbackFunc = Callable[[CallbackData], ResponseType]
AsyncCallbackFunc = Callable[[CallbackData], ResponseType]


@dataclass
class ServerStats:
    """服务器统计信息"""
    total_requests: int = 0
    active_requests: int = 0
    total_errors: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    ratelimit_hits: int = 0
    average_response_time: float = 0.0
    uptime: float = 0.0
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "total_requests": self.total_requests,
            "active_requests": self.active_requests,
            "total_errors": self.total_errors,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "ratelimit_hits": self.ratelimit_hits,
            "average_response_time": self.average_response_time,
            "uptime": self.uptime
        }


@dataclass
class CacheConfig:
    """缓存配置"""
    enabled: bool = True
    ttl: int = 300  # 秒
    max_size: int = 1000
    
    
@dataclass
class RateLimitConfig:
    """限流配置"""
    enabled: bool = True
    max_requests: int = 100
    window: int = 60  # 秒