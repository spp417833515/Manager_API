#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
响应处理模块
处理各种类型的响应格式
"""

import json
from typing import Any, Dict, Optional, Union
from fastapi import Response
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse
from .types import ResponseData, ResponseType
import logging

logger = logging.getLogger(__name__)


class ResponseHandler:
    """响应处理器"""
    
    @staticmethod
    def process_response(data: ResponseType) -> Response:
        """
        处理回调函数返回的数据
        
        Args:
            data: 回调函数返回的数据
            
        Returns:
            FastAPI Response对象
        """
        # None -> 204 No Content
        if data is None:
            return Response(status_code=204)
        
        # 字符串 -> 文本响应
        if isinstance(data, str):
            return PlainTextResponse(content=data)
        
        # 字节 -> 二进制响应
        if isinstance(data, bytes):
            return Response(content=data, media_type="application/octet-stream")
        
        # ResponseData对象 -> 自定义响应
        if isinstance(data, ResponseData):
            return ResponseHandler._create_response_from_data(data)
        
        # 字典 -> JSON响应
        if isinstance(data, dict):
            # 检查是否包含status等特殊字段
            if 'status' in data and ('data' in data or 'headers' in data or 'cookies' in data):
                return ResponseHandler._create_response_from_dict(data)
            
            # 普通字典，直接返回JSON
            return JSONResponse(content=data)
        
        # 列表 -> JSON响应
        if isinstance(data, (list, tuple)):
            return JSONResponse(content=data)
        
        # 其他类型，尝试转换为JSON
        try:
            json_data = json.dumps(data, default=str)
            return JSONResponse(content=json.loads(json_data))
        except Exception as e:
            logger.error(f"Failed to serialize response: {e}")
            return JSONResponse(
                content={"error": "Internal server error"},
                status_code=500
            )
    
    @staticmethod
    def _create_response_from_data(data: ResponseData) -> Response:
        """从ResponseData对象创建响应"""
        return ResponseHandler._create_json_response(
            content=data.data,
            status_code=data.status,
            headers=data.headers,
            cookies=data.cookies
        )
    
    @staticmethod
    def _create_response_from_dict(data: dict) -> Response:
        """从包含status的字典创建响应"""
        return ResponseHandler._create_json_response(
            content=data.get('data', {}),
            status_code=data.get('status', 200),
            headers=data.get('headers', {}),
            cookies=data.get('cookies', {})
        )
    
    @staticmethod
    def _create_json_response(content: Any, status_code: int = 200, 
                            headers: Dict[str, str] = None, 
                            cookies: Dict[str, str] = None) -> Response:
        """创建JSON响应的通用方法"""
        response = JSONResponse(content=content, status_code=status_code)
        
        # 添加headers
        if headers:
            for key, value in headers.items():
                response.headers[key] = value
        
        # 添加cookies
        if cookies:
            for key, value in cookies.items():
                response.set_cookie(key=key, value=value)
        
        return response
    
    @staticmethod
    def error_response(error: Exception, status_code: int = 500) -> Response:
        """创建错误响应"""
        return ResponseHandler._create_json_response(
            content={"error": str(error), "type": type(error).__name__},
            status_code=status_code
        )
    
    @staticmethod
    def not_found_response(path: str) -> Response:
        """创建404响应"""
        return ResponseHandler._create_json_response(
            content={
                "error": "Not Found",
                "path": path,
                "message": f"The requested path '{path}' was not found"
            },
            status_code=404
        )
    
    @staticmethod
    def rate_limit_response() -> Response:
        """创建限流响应"""
        return ResponseHandler._create_json_response(
            content={
                "error": "Rate Limit Exceeded",
                "message": "Too many requests. Please try again later."
            },
            status_code=429
        )
    
    @staticmethod
    def service_unavailable_response() -> Response:
        """创建服务不可用响应"""
        return ResponseHandler._create_json_response(
            content={
                "error": "Service Unavailable",
                "message": "The server is currently unable to handle the request due to temporary overload."
            },
            status_code=503
        )
