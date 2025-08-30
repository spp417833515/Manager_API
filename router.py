#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路由管理模块
管理API路由注册和匹配
"""

from typing import Dict, List, Optional, Any, Tuple
from .types import RouteInfo, HTTPMethod
from .utils import parse_path_params, validate_path
import re
import logging

logger = logging.getLogger(__name__)


class RouteNode:
    """路由树节点"""
    
    def __init__(self):
        self.children: Dict[str, RouteNode] = {}
        self.param_child: Optional[RouteNode] = None
        self.param_name: Optional[str] = None
        self.route_info: Optional[RouteInfo] = None
        self.is_wildcard = False


class RouteTree:
    """路由树实现（用于高效路由匹配）"""
    
    def __init__(self):
        self.root = RouteNode()
    
    def add(self, path: str, route_info: RouteInfo):
        """添加路由"""
        parts = path.strip('/').split('/')
        node = self.root
        
        for part in parts:
            if part.startswith('{') and part.endswith('}'):
                # 路径参数
                param_name = part[1:-1]
                if not node.param_child:
                    node.param_child = RouteNode()
                    node.param_name = param_name
                node = node.param_child
            else:
                # 普通路径
                if part not in node.children:
                    node.children[part] = RouteNode()
                node = node.children[part]
        
        node.route_info = route_info
    
    def find(self, path: str) -> Tuple[Optional[RouteInfo], Dict[str, str]]:
        """查找路由"""
        parts = path.strip('/').split('/')
        params = {}
        
        def search(node: RouteNode, index: int) -> Optional[RouteNode]:
            if index >= len(parts):
                return node if node.route_info else None
            
            part = parts[index]
            
            # 先尝试精确匹配
            if part in node.children:
                result = search(node.children[part], index + 1)
                if result:
                    return result
            
            # 尝试参数匹配
            if node.param_child:
                params[node.param_name] = part
                result = search(node.param_child, index + 1)
                if result:
                    return result
                # 如果参数匹配失败，清除参数
                del params[node.param_name]
            
            return None
        
        result_node = search(self.root, 0)
        if result_node:
            return result_node.route_info, params
        
        return None, {}


class RouterRegistry:
    """路由注册管理器"""
    
    def __init__(self):
        # 按方法分组的路由树
        self.trees: Dict[str, RouteTree] = {}
        
        # 所有路由列表（用于展示）
        self.routes: List[RouteInfo] = []
        
        # 路由分组
        self.groups: Dict[str, List[RouteInfo]] = {}
    
    def register(self, method: str, path: str, 
                group: str = "default",
                name: str = "",
                cache: Optional[bool] = None,
                ratelimit: Optional[Dict[str, int]] = None,
                auth: bool = False,
                **options) -> bool:
        """
        注册路由
        
        Args:
            method: HTTP方法
            path: 路由路径
            group: 分组名称
            name: 路由名称
            cache: 是否缓存
            ratelimit: 限流配置
            auth: 是否需要认证
            **options: 其他选项
            
        Returns:
            是否注册成功
        """
        # 验证路径格式
        if not validate_path(path):
            logger.error(f"Invalid path format: {path}")
            return False
        
        # 转换方法为大写
        method = method.upper()
        
        # 创建路由信息
        route_info = RouteInfo(
            method=method,
            path=path,
            group=group,
            name=name or path,
            cache=cache,
            ratelimit=ratelimit,
            auth=auth,
            options=options
        )
        
        # 添加到路由树
        if method not in self.trees:
            self.trees[method] = RouteTree()
        
        self.trees[method].add(path, route_info)
        
        # 添加到路由列表
        self.routes.append(route_info)
        
        # 添加到分组
        if group not in self.groups:
            self.groups[group] = []
        self.groups[group].append(route_info)
        
        logger.info(f"Registered route: {method} {path} (group={group}, name={name})")
        return True
    
    def find_route(self, method: str, path: str) -> Tuple[Optional[RouteInfo], Dict[str, str]]:
        """
        查找匹配的路由
        
        Args:
            method: HTTP方法
            path: 请求路径
            
        Returns:
            (路由信息, 路径参数)
        """
        method = method.upper()
        
        # 如果方法不存在，返回None
        if method not in self.trees:
            return None, {}
        
        # 在路由树中查找
        route_info, params = self.trees[method].find(path)
        
        if route_info:
            return route_info, params
        
        # 如果没找到，尝试模糊匹配（向后兼容）
        for route in self.routes:
            if route.method == method:
                params = parse_path_params(route.path, path)
                if params is not None:
                    return route, params
        
        return None, {}
    
    def get_routes(self) -> List[RouteInfo]:
        """获取所有路由"""
        return self.routes.copy()
    
    def get_routes_by_group(self, group: str) -> List[RouteInfo]:
        """获取指定分组的路由"""
        return self.groups.get(group, []).copy()
    
    def get_groups(self) -> List[str]:
        """获取所有分组"""
        return list(self.groups.keys())
    
    def get_route_stats(self) -> Dict[str, Any]:
        """获取路由统计信息"""
        method_counts = {}
        for route in self.routes:
            method = route.method
            method_counts[method] = method_counts.get(method, 0) + 1
        
        return {
            'total': len(self.routes),
            'groups': len(self.groups),
            'methods': method_counts,
            'cached': sum(1 for r in self.routes if r.cache),
            'rate_limited': sum(1 for r in self.routes if r.ratelimit),
            'auth_required': sum(1 for r in self.routes if r.auth)
        }
    
    def clear(self):
        """清空所有路由"""
        self.trees.clear()
        self.routes.clear()
        self.groups.clear()
        logger.info("All routes cleared")
    
    def remove_route(self, method: str, path: str) -> bool:
        """
        移除路由
        
        Args:
            method: HTTP方法
            path: 路由路径
            
        Returns:
            是否移除成功
        """
        method = method.upper()
        
        # 从路由列表中移除
        for i, route in enumerate(self.routes):
            if route.method == method and route.path == path:
                # 从分组中移除
                group = route.group
                if group in self.groups:
                    self.groups[group] = [r for r in self.groups[group] 
                                         if not (r.method == method and r.path == path)]
                    if not self.groups[group]:
                        del self.groups[group]
                
                # 从路由列表中移除
                del self.routes[i]
                
                # TODO: 从路由树中移除（需要重建树）
                self._rebuild_trees()
                
                logger.info(f"Removed route: {method} {path}")
                return True
        
        return False
    
    def _rebuild_trees(self):
        """重建路由树"""
        self.trees.clear()
        for route in self.routes:
            if route.method not in self.trees:
                self.trees[route.method] = RouteTree()
            self.trees[route.method].add(route.path, route)