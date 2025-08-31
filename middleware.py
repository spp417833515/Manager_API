#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中间件管理模块
处理CORS、日志、错误等中间件
"""

from typing import List, Dict, Any
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from .utils import match_cors_origin, get_client_ip
from .response import FormattedJSONResponse
import time
import logging

logger = logging.getLogger(__name__)


class CustomCORSMiddleware(BaseHTTPMiddleware):
    """自定义CORS中间件（支持通配符）"""
    
    def __init__(self, app, allowed_origins: List[str], 
                 allow_credentials: bool = True,
                 allow_methods: List[str] = None,
                 allow_headers: List[str] = None):
        super().__init__(app)
        self.allowed_origins = allowed_origins
        self.allow_credentials = allow_credentials
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
    
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        
        # 处理预检请求
        if request.method == "OPTIONS":
            response = Response()
            response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
            response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
            
            if origin and match_cors_origin(origin, self.allowed_origins):
                response.headers["Access-Control-Allow-Origin"] = origin
                if self.allow_credentials:
                    response.headers["Access-Control-Allow-Credentials"] = "true"
            
            return response
        
        # 处理普通请求
        response = await call_next(request)
        
        if origin and match_cors_origin(origin, self.allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            if self.allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件"""
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = get_client_ip(request)
        
        # 记录请求
        logger.info(f"Request: {request.method} {request.url.path} from {client_ip}")
        
        try:
            response = await call_next(request)
            
            # 记录响应
            duration = time.time() - start_time
            logger.info(
                f"Response: {response.status_code} for "
                f"{request.method} {request.url.path} "
                f"({duration:.3f}s)"
            )
            
            # 添加响应时间header
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Error handling {request.method} {request.url.path}: {e} "
                f"({duration:.3f}s)"
            )
            raise


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """错误处理中间件"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"Unhandled exception: {e}", exc_info=True)
            
            # 返回错误响应
            from .response import ResponseHandler
            return ResponseHandler.error_response(e, 500)


class RequestSizeMiddleware(BaseHTTPMiddleware):
    """请求大小限制中间件"""
    
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # 默认10MB
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size:
                    return FormattedJSONResponse(
                        content={
                            "error": "Request Entity Too Large",
                            "message": f"Request size {size} exceeds maximum allowed size {self.max_size}"
                        },
                        status_code=413
                    )
            except ValueError:
                pass
        
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全headers中间件"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 添加安全headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """请求ID中间件"""
    
    async def dispatch(self, request: Request, call_next):
        from .utils import generate_request_id
        
        # 生成或获取请求ID
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        
        # 将请求ID添加到request状态
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        # 在响应中添加请求ID
        response.headers["X-Request-ID"] = request_id
        
        return response


class MiddlewareManager:
    """中间件管理器"""
    
    def __init__(self, app):
        self.app = app
        self.middlewares = []
    
    def add_cors(self, enabled: bool, origins: List[str]):
        """添加CORS中间件"""
        if enabled and origins:
            self.app.add_middleware(
                CustomCORSMiddleware,
                allowed_origins=origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"]
            )
            logger.info(f"CORS middleware added with origins: {origins}")
    
    def add_logging(self, enabled: bool = True):
        """添加日志中间件"""
        if enabled:
            self.app.add_middleware(LoggingMiddleware)
            logger.info("Logging middleware added")
    
    def add_error_handling(self, enabled: bool = True):
        """添加错误处理中间件"""
        if enabled:
            self.app.add_middleware(ErrorHandlingMiddleware)
            logger.info("Error handling middleware added")
    
    def add_request_size_limit(self, max_size: int = 10 * 1024 * 1024):
        """添加请求大小限制中间件"""
        self.app.add_middleware(RequestSizeMiddleware, max_size=max_size)
        logger.info(f"Request size limit middleware added (max: {max_size} bytes)")
    
    def add_security_headers(self, enabled: bool = True):
        """添加安全headers中间件"""
        if enabled:
            self.app.add_middleware(SecurityHeadersMiddleware)
            logger.info("Security headers middleware added")
    
    def add_request_id(self, enabled: bool = True):
        """添加请求ID中间件"""
        if enabled:
            self.app.add_middleware(RequestIDMiddleware)
            logger.info("Request ID middleware added")