#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
提供各种辅助功能
"""

import hashlib
import time
import uuid
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
import asyncio
from functools import wraps
import logging

logger = logging.getLogger(__name__)


def generate_request_id() -> str:
    """生成请求ID"""
    return str(uuid.uuid4())


def get_client_ip(request) -> str:
    """获取客户端IP"""
    if hasattr(request, 'client'):
        return request.client.host if request.client else "127.0.0.1"
    
    # 尝试从headers中获取
    headers = getattr(request, 'headers', {})
    for header in ['x-forwarded-for', 'x-real-ip']:
        if header in headers:
            ip = headers[header].split(',')[0].strip()
            if ip:
                return ip
    
    return "127.0.0.1"


def match_cors_origin(origin: str, allowed_origins: List[str]) -> bool:
    """
    匹配CORS源
    支持通配符匹配，如 http://192.168.1.*
    """
    if not origin:
        return False
    
    for allowed in allowed_origins:
        if allowed == "*":
            return True
        
        # 支持通配符匹配
        if "*" in allowed:
            pattern = allowed.replace(".", r"\.").replace("*", ".*")
            if re.match(f"^{pattern}$", origin):
                return True
        elif origin == allowed:
            return True
    
    return False


def parse_path_params(path_template: str, actual_path: str) -> Optional[Dict[str, str]]:
    """
    解析路径参数
    例如: /api/users/{id} 匹配 /api/users/123 -> {"id": "123"}
    """
    # 将路径模板转换为正则表达式
    pattern = path_template
    param_names = []
    
    # 查找所有 {param} 格式的参数
    for match in re.finditer(r'\{(\w+)\}', path_template):
        param_names.append(match.group(1))
        pattern = pattern.replace(match.group(0), r'([^/]+)')
    
    # 如果没有参数，直接比较
    if not param_names:
        return {} if path_template == actual_path else None
    
    # 匹配路径
    pattern = f"^{pattern}$"
    match = re.match(pattern, actual_path)
    
    if match:
        return dict(zip(param_names, match.groups()))
    
    return None


def generate_cache_key(method: str, path: str, query: Dict[str, Any]) -> str:
    """生成缓存键"""
    key_parts = [method, path]
    
    # 添加排序后的查询参数
    if query:
        sorted_query = sorted(query.items())
        query_str = "&".join([f"{k}={v}" for k, v in sorted_query])
        key_parts.append(query_str)
    
    key_string = "|".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """格式化时间长度"""
    if seconds < 1:
        return f"{seconds*1000:.2f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        return f"{seconds/60:.2f}m"
    else:
        return f"{seconds/3600:.2f}h"


def safe_json_dumps(obj: Any) -> str:
    """安全的JSON序列化"""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, bytes):
            return o.decode('utf-8', errors='ignore')
        elif hasattr(o, '__dict__'):
            return o.__dict__
        else:
            return str(o)
    
    return json.dumps(obj, default=default, ensure_ascii=False)


def async_to_sync(func):
    """将异步函数转换为同步函数的装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # 如果已经在事件循环中，创建任务
            return asyncio.create_task(func(*args, **kwargs))
        else:
            # 如果不在事件循环中，创建新的事件循环
            return asyncio.run(func(*args, **kwargs))
    
    return wrapper


def sync_to_async(func):
    """将同步函数转换为异步函数的装饰器"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)
    
    return wrapper



def validate_path(path: str) -> bool:
    """验证路径格式是否合法"""
    if not path:
        return False
    
    # 路径必须以 / 开头
    if not path.startswith('/'):
        return False
    
    # 不允许连续的斜杠
    if '//' in path:
        return False
    
    # 验证路径参数格式
    if '{' in path:
        # 确保所有花括号都是成对的
        if path.count('{') != path.count('}'):
            return False
        
        # 确保参数名称合法
        for match in re.finditer(r'\{(\w*)\}', path):
            param_name = match.group(1)
            if not param_name:
                return False
    
    return True


def merge_dict(base: dict, override: dict) -> dict:
    """合并两个字典，override中的值会覆盖base中的值"""
    result = base.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = value
    return result