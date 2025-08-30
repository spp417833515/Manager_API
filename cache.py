#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存系统模块
提供高性能的内存缓存功能
"""

import time
import asyncio
from typing import Any, Optional, Dict
from collections import OrderedDict
from threading import RLock
import hashlib
import logging

logger = logging.getLogger(__name__)


class CacheEntry:
    """缓存条目"""
    
    def __init__(self, data: Any, ttl: int = 300):
        self.data = data
        self.timestamp = time.time()
        self.ttl = ttl
        self.access_count = 0
        self.last_access = self.timestamp
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return time.time() - self.timestamp > self.ttl
    
    def access(self) -> Any:
        """访问缓存"""
        self.access_count += 1
        self.last_access = time.time()
        return self.data


class LRUCache:
    """LRU缓存实现"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired': 0
        }
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # 检查过期
            if entry.is_expired():
                del self.cache[key]
                self.stats['expired'] += 1
                self.stats['misses'] += 1
                return None
            
            # 移动到末尾（最近使用）
            self.cache.move_to_end(key)
            self.stats['hits'] += 1
            return entry.access()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        with self.lock:
            # 如果已存在，删除旧的
            if key in self.cache:
                del self.cache[key]
            
            # 检查容量
            while len(self.cache) >= self.max_size:
                # 删除最久未使用的（第一个）
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats['evictions'] += 1
            
            # 添加新缓存
            ttl = ttl or self.default_ttl
            self.cache[key] = CacheEntry(value, ttl)
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.stats = {
                'hits': 0,
                'misses': 0,
                'evictions': 0,
                'expired': 0
            }
    
    def cleanup(self):
        """清理过期缓存"""
        with self.lock:
            expired_keys = []
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
                self.stats['expired'] += 1
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            total = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total * 100) if total > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': f"{hit_rate:.2f}%",
                'evictions': self.stats['evictions'],
                'expired': self.stats['expired']
            }
    
    def get_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        with self.lock:
            entries = []
            for key, entry in list(self.cache.items())[:10]:  # 只显示前10个
                entries.append({
                    'key': key,
                    'age': time.time() - entry.timestamp,
                    'ttl': entry.ttl,
                    'access_count': entry.access_count
                })
            
            return {
                'entries': entries,
                'total': len(self.cache)
            }


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, enabled: bool = True, max_size: int = 1000, default_ttl: int = 300):
        self.enabled = enabled
        self.cache = LRUCache(max_size, default_ttl) if enabled else None
        self._cleanup_task = None
        self._cleanup_interval = 60  # 清理间隔（秒）
    
    async def start(self):
        """启动缓存管理器"""
        if self.enabled and not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Cache manager started")
    
    async def stop(self):
        """停止缓存管理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Cache manager stopped")
    
    async def _cleanup_loop(self):
        """定期清理过期缓存"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                if self.cache:
                    expired = self.cache.cleanup()
                    if expired > 0:
                        logger.debug(f"Cleaned up {expired} expired cache entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if not self.enabled or not self.cache:
            return None
        return self.cache.get(key)
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存"""
        if self.enabled and self.cache:
            self.cache.set(key, value, ttl)
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        if not self.enabled or not self.cache:
            return False
        return self.cache.delete(key)
    
    def clear(self):
        """清空缓存"""
        if self.cache:
            self.cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.cache:
            return {'enabled': False}
        
        stats = self.cache.get_stats()
        stats['enabled'] = self.enabled
        return stats
    
    def get_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        if not self.cache:
            return {'enabled': False}
        
        info = self.cache.get_info()
        info['enabled'] = self.enabled
        return info