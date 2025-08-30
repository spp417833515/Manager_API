#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manager_API - 高性能简洁API服务器框架

主要特性:
- 基于FastAPI构建，高性能异步支持
- 内置并发控制、缓存、限流、监控
- 简单的回调式路由处理
- 自动CORS配置
- 实时监控面板

快速开始:
    from Manager_API import FastAPIServer
    
    # 创建服务器
    server = FastAPIServer()
    server.host = '0.0.0.0'
    server.port = 8000
    server.title = "My API"
    
    # 注册路由
    server.append("GET", "/api/hello")
    server.append("POST", "/api/data")
    
    # 设置处理函数
    @server.callback
    def handle(data):
        if data['path'] == '/api/hello':
            return {"message": "Hello World"}
        elif data['path'] == '/api/data':
            return {"received": data['body']}
    
    # 启动服务
    server.start()
"""

from .server import FastAPIServer
from .types import CallbackData, ResponseData
from .response import ResponseHandler

__version__ = "3.1.0"
__author__ = "Manager API Team"
__all__ = [
    "FastAPIServer",
    "CallbackData", 
    "ResponseData",
    "ResponseHandler"
]