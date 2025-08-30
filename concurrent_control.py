#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并发控制模块
管理请求并发数，防止服务器过载
"""

import asyncio
import time
from typing import Optional, Dict, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)


class ConcurrencyManager:
    """并发控制管理器"""
    
    def __init__(self, max_concurrent: int = 1000, queue_timeout: int = 30):
        """
        初始化并发管理器
        
        Args:
            max_concurrent: 最大并发数
            queue_timeout: 队列等待超时时间（秒）
        """
        self.max_concurrent = max_concurrent
        self.queue_timeout = queue_timeout
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # 统计信息
        self.current_active = 0
        self.total_processed = 0
        self.total_rejected = 0
        self.total_timeout = 0
        self.queue = deque()
        self.max_queue_size = max_concurrent * 2  # 队列最大长度
        
        # 性能监控
        self.response_times = deque(maxlen=1000)  # 保留最近1000个请求的响应时间
        self._lock = asyncio.Lock()
    
    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        获取执行权限
        
        Args:
            timeout: 超时时间
            
        Returns:
            是否成功获取
        """
        timeout = timeout or self.queue_timeout
        
        async with self._lock:
            # 检查队列是否已满
            if len(self.queue) >= self.max_queue_size:
                self.total_rejected += 1
                logger.warning(f"Request rejected: queue full ({self.max_queue_size})")
                return False
        
        try:
            # 尝试获取信号量
            await asyncio.wait_for(self.semaphore.acquire(), timeout=timeout)
            
            async with self._lock:
                self.current_active += 1
                self.total_processed += 1
            
            return True
            
        except asyncio.TimeoutError:
            async with self._lock:
                self.total_timeout += 1
            logger.warning(f"Request timeout: waited {timeout}s")
            return False
        
        except Exception as e:
            logger.error(f"Error acquiring semaphore: {e}")
            return False
    
    def release(self):
        """释放执行权限"""
        self.semaphore.release()
        
        # 更新统计
        asyncio.create_task(self._update_stats_on_release())
    
    async def _update_stats_on_release(self):
        """释放时更新统计信息"""
        async with self._lock:
            self.current_active = max(0, self.current_active - 1)
    
    async def execute_with_limit(self, func, *args, **kwargs):
        """
        在并发限制下执行函数
        
        Args:
            func: 要执行的函数
            *args, **kwargs: 函数参数
            
        Returns:
            函数执行结果
        """
        start_time = time.time()
        acquired = False
        
        try:
            # 获取执行权限
            acquired = await self.acquire()
            if not acquired:
                raise RuntimeError("Failed to acquire concurrency slot")
            
            # 执行函数
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 记录响应时间
            response_time = time.time() - start_time
            self.response_times.append(response_time)
            
            return result
            
        finally:
            if acquired:
                self.release()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        avg_response_time = 0
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
        
        return {
            'max_concurrent': self.max_concurrent,
            'current_active': self.current_active,
            'total_processed': self.total_processed,
            'total_rejected': self.total_rejected,
            'total_timeout': self.total_timeout,
            'queue_size': len(self.queue),
            'max_queue_size': self.max_queue_size,
            'avg_response_time': f"{avg_response_time:.3f}s",
            'utilization': f"{(self.current_active / self.max_concurrent * 100):.1f}%"
        }
    
    def update_limit(self, new_limit: int):
        """
        动态更新并发限制
        
        Args:
            new_limit: 新的并发限制
        """
        if new_limit <= 0:
            raise ValueError("Concurrent limit must be positive")
        
        old_limit = self.max_concurrent
        self.max_concurrent = new_limit
        
        # 重新创建信号量
        self.semaphore = asyncio.Semaphore(new_limit)
        self.max_queue_size = new_limit * 2
        
        logger.info(f"Concurrency limit updated from {old_limit} to {new_limit}")
    
    def is_overloaded(self) -> bool:
        """检查是否过载"""
        return self.current_active >= self.max_concurrent * 0.9
    
    def get_queue_position(self) -> int:
        """获取当前队列位置"""
        return len(self.queue)


