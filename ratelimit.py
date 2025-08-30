#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
限流系统模块
实现令牌桶和滑动窗口算法
"""

import time
import asyncio
from typing import Dict, Optional, Any
from collections import defaultdict, deque
from threading import RLock
import logging

logger = logging.getLogger(__name__)


class TokenBucket:
    """令牌桶算法实现"""
    
    def __init__(self, rate: int, capacity: int):
        """
        初始化令牌桶
        
        Args:
            rate: 每秒生成的令牌数
            capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self.lock = RLock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        消费令牌
        
        Args:
            tokens: 需要消费的令牌数
            
        Returns:
            是否成功消费
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update
        
        # 计算应该生成的令牌数
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_update = now
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """
        获取需要等待的时间
        
        Args:
            tokens: 需要的令牌数
            
        Returns:
            需要等待的秒数
        """
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                return 0.0
            
            needed = tokens - self.tokens
            return needed / self.rate


class SlidingWindow:
    """滑动窗口算法实现"""
    
    def __init__(self, window_size: int, max_requests: int):
        """
        初始化滑动窗口
        
        Args:
            window_size: 窗口大小（秒）
            max_requests: 窗口内最大请求数
        """
        self.window_size = window_size
        self.max_requests = max_requests
        self.requests = deque()
        self.lock = RLock()
    
    def allow_request(self) -> bool:
        """
        检查是否允许请求
        
        Returns:
            是否允许
        """
        with self.lock:
            now = time.time()
            
            # 清理过期请求
            while self.requests and self.requests[0] <= now - self.window_size:
                self.requests.popleft()
            
            # 检查是否超过限制
            if len(self.requests) >= self.max_requests:
                return False
            
            # 记录新请求
            self.requests.append(now)
            return True
    
    def get_remaining(self) -> int:
        """获取剩余可用请求数"""
        with self.lock:
            now = time.time()
            
            # 清理过期请求
            while self.requests and self.requests[0] <= now - self.window_size:
                self.requests.popleft()
            
            return max(0, self.max_requests - len(self.requests))


class RateLimiter:
    """限流器"""
    
    def __init__(self, max_requests: int = 100, window: int = 60, 
                 algorithm: str = "sliding_window"):
        """
        初始化限流器
        
        Args:
            max_requests: 最大请求数
            window: 时间窗口（秒）
            algorithm: 算法类型 (sliding_window 或 token_bucket)
        """
        self.max_requests = max_requests
        self.window = window
        self.algorithm = algorithm
        
        if algorithm == "token_bucket":
            rate = max_requests / window
            self.limiter = TokenBucket(rate, max_requests)
        else:
            self.limiter = SlidingWindow(window, max_requests)
        
        # 统计信息
        self.stats = {
            'allowed': 0,
            'rejected': 0,
            'total': 0
        }
    
    def check(self) -> bool:
        """
        检查是否允许请求
        
        Returns:
            是否允许
        """
        self.stats['total'] += 1
        
        if isinstance(self.limiter, TokenBucket):
            allowed = self.limiter.consume()
        else:
            allowed = self.limiter.allow_request()
        
        if allowed:
            self.stats['allowed'] += 1
        else:
            self.stats['rejected'] += 1
        
        return allowed
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'algorithm': self.algorithm,
            'max_requests': self.max_requests,
            'window': self.window,
            'allowed': self.stats['allowed'],
            'rejected': self.stats['rejected'],
            'total': self.stats['total'],
            'reject_rate': f"{(self.stats['rejected'] / max(1, self.stats['total']) * 100):.2f}%"
        }


class RateLimitManager:
    """限流管理器"""
    
    def __init__(self, enabled: bool = True, 
                 default_max_requests: int = 100,
                 default_window: int = 60):
        """
        初始化限流管理器
        
        Args:
            enabled: 是否启用限流
            default_max_requests: 默认最大请求数
            default_window: 默认时间窗口
        """
        self.enabled = enabled
        self.default_max_requests = default_max_requests
        self.default_window = default_window
        
        # 不同路径的限流器
        self.limiters: Dict[str, RateLimiter] = {}
        
        # 基于IP的限流器
        self.ip_limiters: Dict[str, RateLimiter] = {}
        
        # 全局限流器
        self.global_limiter = RateLimiter(
            default_max_requests * 10,  # 全局限制更宽松
            default_window
        ) if enabled else None
        
        self.lock = RLock()
    
    def check_request(self, path: str, client_ip: str, 
                      custom_config: Optional[Dict[str, int]] = None) -> bool:
        """
        检查请求是否被限流
        
        Args:
            path: 请求路径
            client_ip: 客户端IP
            custom_config: 自定义限流配置
            
        Returns:
            是否允许请求
        """
        if not self.enabled:
            return True
        
        # 检查全局限流
        if self.global_limiter and not self.global_limiter.check():
            logger.warning(f"Global rate limit exceeded")
            return False
        
        # 检查IP限流
        if not self._check_ip_limit(client_ip):
            logger.warning(f"IP rate limit exceeded for {client_ip}")
            return False
        
        # 检查路径限流
        if custom_config:
            if not self._check_path_limit(path, custom_config):
                logger.warning(f"Path rate limit exceeded for {path}")
                return False
        
        return True
    
    def _check_ip_limit(self, client_ip: str) -> bool:
        """检查IP限流"""
        with self.lock:
            if client_ip not in self.ip_limiters:
                self.ip_limiters[client_ip] = RateLimiter(
                    self.default_max_requests,
                    self.default_window
                )
            
            return self.ip_limiters[client_ip].check()
    
    def _check_path_limit(self, path: str, config: Dict[str, int]) -> bool:
        """检查路径限流"""
        with self.lock:
            if path not in self.limiters:
                max_requests = config.get('max', self.default_max_requests)
                window = config.get('window', self.default_window)
                self.limiters[path] = RateLimiter(max_requests, window)
            
            return self.limiters[path].check()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'enabled': self.enabled,
            'global': self.global_limiter.get_stats() if self.global_limiter else None,
            'paths': {},
            'ips': {}
        }
        
        # 获取前10个路径的统计
        for path, limiter in list(self.limiters.items())[:10]:
            stats['paths'][path] = limiter.get_stats()
        
        # 获取前10个IP的统计
        for ip, limiter in list(self.ip_limiters.items())[:10]:
            stats['ips'][ip] = limiter.get_stats()
        
        return stats
    
    def cleanup(self):
        """清理过期的限流器"""
        with self.lock:
            # 可以实现定期清理逻辑
            pass