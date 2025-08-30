#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
请求处理模块
处理HTTP请求并调用用户回调
"""

import time
import json
import asyncio
from typing import Any, Dict, Optional, List
from fastapi import Request, UploadFile, File
from .types import CallbackData, CallbackFunc, AsyncCallbackFunc
from .utils import generate_request_id, get_client_ip, generate_cache_key
from .response import ResponseHandler
import logging

logger = logging.getLogger(__name__)


class RequestHandler:
    """请求处理器"""
    
    def __init__(self):
        self.callback: Optional[CallbackFunc] = None
        self.is_async_callback = False
    
    def set_callback(self, func: CallbackFunc):
        """设置回调函数"""
        self.callback = func
        self.is_async_callback = asyncio.iscoroutinefunction(func)
        logger.info(f"Callback set: {'async' if self.is_async_callback else 'sync'} function")
    
    async def process_request(self, 
                             request: Request,
                             method: str,
                             path: str,
                             route_info: Dict[str, Any],
                             path_params: Dict[str, str]) -> Any:
        """
        处理请求
        
        Args:
            request: FastAPI请求对象
            method: HTTP方法
            path: 请求路径
            route_info: 路由信息
            path_params: 路径参数
            
        Returns:
            处理结果
        """
        if not self.callback:
            logger.error("No callback function set")
            return ResponseHandler.error_response(
                Exception("No callback function configured"),
                500
            )
        
        try:
            # 构建回调数据
            callback_data = await self._build_callback_data(
                request, method, path, route_info, path_params
            )
            
            # 调用回调函数
            if self.is_async_callback:
                result = await self.callback(callback_data)
            else:
                result = self.callback(callback_data)
            
            # 处理响应
            return ResponseHandler.process_response(result)
            
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            return ResponseHandler.error_response(e, 500)
    
    async def _build_callback_data(self,
                                  request: Request,
                                  method: str,
                                  path: str,
                                  route_info: Dict[str, Any],
                                  path_params: Dict[str, str]) -> CallbackData:
        """构建回调数据"""
        # 获取查询参数
        query_params = dict(request.query_params)
        
        # 获取请求体
        body = await self._get_request_body(request)
        
        # 获取文件
        files = await self._get_uploaded_files(request)
        
        # 获取headers
        headers = dict(request.headers)
        
        # 获取cookies
        cookies = request.cookies
        
        # 构建回调数据
        callback_data: CallbackData = {
            'type': method,
            'path': path,
            'method': method,  # 兼容性
            'params': path_params,
            'query': query_params,
            'body': body,
            'headers': headers,
            'cookies': cookies,
            'client': get_client_ip(request),
            'request_id': generate_request_id(),
            'timestamp': time.time(),
            'route_info': route_info
        }
        
        # 如果有文件，添加到数据中
        if files:
            callback_data['files'] = files
        
        return callback_data
    
    async def _get_request_body(self, request: Request) -> Any:
        """获取请求体"""
        content_type = request.headers.get('content-type', '')
        
        try:
            if 'application/json' in content_type:
                # JSON数据
                return await request.json()
            elif 'application/x-www-form-urlencoded' in content_type:
                # 表单数据
                form_data = await request.form()
                return dict(form_data)
            elif 'multipart/form-data' in content_type:
                # 多部分表单（包含文件）
                form_data = await request.form()
                # 过滤掉文件，只返回普通字段
                return {k: v for k, v in form_data.items() 
                       if not isinstance(v, UploadFile)}
            else:
                # 原始数据
                body_bytes = await request.body()
                if body_bytes:
                    # 尝试解析为JSON
                    try:
                        return json.loads(body_bytes)
                    except:
                        # 返回字符串
                        return body_bytes.decode('utf-8', errors='ignore')
                return None
        except Exception as e:
            logger.warning(f"Failed to parse request body: {e}")
            return None
    
    async def _get_uploaded_files(self, request: Request) -> List[Dict[str, Any]]:
        """获取上传的文件"""
        files = []
        
        try:
            content_type = request.headers.get('content-type', '')
            if 'multipart/form-data' in content_type:
                form_data = await request.form()
                for key, value in form_data.items():
                    if isinstance(value, UploadFile):
                        file_info = {
                            'field_name': key,
                            'filename': value.filename,
                            'content_type': value.content_type,
                            'size': value.size if hasattr(value, 'size') else None,
                            'file': value  # 保留原始文件对象
                        }
                        files.append(file_info)
        except Exception as e:
            logger.warning(f"Failed to get uploaded files: {e}")
        
        return files
