#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主服务器类
FastAPI服务器的核心实现
"""

import uvicorn
import logging
import time
import json
from typing import Optional, Dict, Any
from threading import Thread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

# 导入内部模块
from .types import CallbackFunc
from .router import RouterRegistry
from .handlers import RequestHandler
from .middleware import MiddlewareManager
from .cache import CacheManager
from .concurrent_control import ConcurrencyManager
from .ratelimit import RateLimitManager
from .monitor import MonitorSystem
from .response import ResponseHandler
from .utils import generate_cache_key, get_client_ip

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FastAPIServer:
    """
    简洁的API服务器
    所有配置通过属性设置，所有请求通过单一回调处理
    """
    
    def __init__(self):
        # 服务器配置（通过属性设置）
        self.host = '0.0.0.0'
        self.port = 8000
        self.title = "API Server"
        self.description = ""
        self.version = "1.0.0"
        self.debug = False
        
        # CORS配置
        self.enable_cors = True
        self.cors = ["*"]  # 支持字符串列表和通配符
        
        # 性能配置
        self.max_concurrent = 1000      # 最大并发数
        self.request_timeout = 60       # 请求超时(秒)
        self.enable_cache = True        # 启用缓存
        self.cache_ttl = 300           # 缓存TTL(秒)
        self.enable_ratelimit = True    # 启用限流
        self.ratelimit_window = 60      # 限流窗口(秒)
        self.ratelimit_max = 100        # 窗口内最大请求数
        
        # 监控配置
        self.enable_monitor = True      # 启用监控
        self.enable_metrics = True      # 启用指标收集
        self.enable_health = True       # 启用健康检查
        
        # 内部组件
        self._app: Optional[FastAPI] = None
        self._callback: Optional[CallbackFunc] = None
        self._is_running = False
        self._server_thread: Optional[Thread] = None
        
        # 管理器
        self._router_registry = RouterRegistry()
        self._request_handler = RequestHandler()
        self._cache_manager: Optional[CacheManager] = None
        self._concurrent_manager: Optional[ConcurrencyManager] = None
        self._ratelimit_manager: Optional[RateLimitManager] = None
        self._monitor_system: Optional[MonitorSystem] = None
        self._middleware_manager: Optional[MiddlewareManager] = None
    
    def append(self, method: str, path: str, 
               group: str = "default", 
               name: str = "",
               cache: Optional[bool] = None,
               ratelimit: Optional[Dict[str, int]] = None,
               auth: bool = False,
               **options):
        """
        注册API路由
        
        参数:
            method: HTTP方法 (GET/POST/PUT/DELETE/PATCH)
            path: 路由路径
            group: API分组（用于文档）
            name: API名称（用于文档）
            cache: 是否缓存（覆盖全局设置）
            ratelimit: 限流配置 {"max": 10, "window": 60}
            auth: 是否需要认证
            **options: 其他扩展选项
        """
        success = self._router_registry.register(
            method, path, group, name, cache, ratelimit, auth, **options
        )
        
        if success:
            logger.info(f"Registered route: {method} {path}")
        else:
            logger.error(f"Failed to register route: {method} {path}")
        
        return success
    
    def callback(self, func: CallbackFunc):
        """
        设置回调函数（装饰器方式）
        
        @server.callback
        def api_handle(data):
            # data包含: type, path, method, params, body, headers, query
            return response
        """
        self.set_callback(func)
        return func
    
    def set_callback(self, func: CallbackFunc):
        """
        设置回调函数（直接设置）
        """
        self._callback = func
        self._request_handler.set_callback(func)
        logger.info("Callback function set")
    
    def start(self, block: bool = False) -> bool:
        """
        启动服务器
        
        参数:
            block: 是否阻塞运行（默认False，非阻塞）
        返回:
            bool: 启动是否成功
        """
        try:
            if self._is_running:
                logger.warning("Server is already running")
                return False
            
            # 初始化FastAPI应用
            self._init_app()
            
            # 先注册系统路由（优先级高）
            self._register_system_routes()
            
            # 再注册用户路由
            self._register_routes()
            
            self._is_running = True
            
            if block:
                # 阻塞运行
                logger.info(f"Starting server at http://{self.host}:{self.port}")
                uvicorn.run(
                    self._app,
                    host=self.host,
                    port=self.port,
                    log_level="info" if self.debug else "error"
                )
            else:
                # 非阻塞运行（在新线程中）
                self._server_thread = Thread(
                    target=lambda: uvicorn.run(
                        self._app,
                        host=self.host,
                        port=self.port,
                        log_level="info" if self.debug else "error"
                    )
                )
                self._server_thread.daemon = True
                self._server_thread.start()
                logger.info(f"Server started in background at http://{self.host}:{self.port}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self._is_running = False
            return False
    
    def stop(self):
        """停止服务器"""
        if not self._is_running:
            logger.warning("Server is not running")
            return
        
        self._is_running = False
        logger.info("Server stopped")
    
    def reload(self):
        """重载服务器配置"""
        if self._is_running:
            logger.info("Reloading server configuration...")
            # 重新初始化管理器
            self._init_managers()
            logger.info("Server configuration reloaded")
    
    def _init_app(self):
        """初始化FastAPI应用"""
        self._app = FastAPI(
            title=self.title,
            description=self.description,
            version=self.version,
            debug=self.debug
        )
        
        # 初始化管理器
        self._init_managers()
        
        # 设置中间件
        self._setup_middleware()
    
    def _init_managers(self):
        """初始化各种管理器"""
        # 缓存管理器
        self._cache_manager = CacheManager(
            enabled=self.enable_cache,
            max_size=1000,
            default_ttl=self.cache_ttl
        )
        
        # 并发管理器
        self._concurrent_manager = ConcurrencyManager(
            max_concurrent=self.max_concurrent,
            queue_timeout=self.request_timeout
        )
        
        # 限流管理器
        self._ratelimit_manager = RateLimitManager(
            enabled=self.enable_ratelimit,
            default_max_requests=self.ratelimit_max,
            default_window=self.ratelimit_window
        )
        
        # 监控系统
        if self.enable_monitor:
            self._monitor_system = MonitorSystem()
            # 设置DEBUG模式
            self._monitor_system.set_debug_mode(self.debug)
    
    def _setup_middleware(self):
        """设置中间件"""
        self._middleware_manager = MiddlewareManager(self._app)
        
        # 添加CORS中间件
        if self.enable_cors:
            self._middleware_manager.add_cors(True, self.cors)
        
        # 添加其他中间件
        self._middleware_manager.add_request_id(True)
        self._middleware_manager.add_logging(self.debug)
        self._middleware_manager.add_error_handling(True)
        self._middleware_manager.add_security_headers(True)
        self._middleware_manager.add_request_size_limit(10 * 1024 * 1024)  # 10MB
    
    def _register_routes(self):
        """注册用户定义的路由"""
        # 创建通用处理函数
        async def handle_request(request: Request, path: str = None):
            """通用请求处理函数"""
            start_time = time.time()
            request_id = None
            
            # 获取请求方法和路径
            method = request.method
            request_path = path or request.url.path
            
            # 记录请求（性能优化：基础统计始终记录，但仅在有监控系统时）
            if self._monitor_system:
                self._monitor_system.record_request()
                
                # 如果是DEBUG模式，记录详细请求信息
                if self.debug:
                    # 解析请求体
                    body = None
                    if method in ["POST", "PUT", "PATCH"]:
                        try:
                            body = await request.json()
                        except:
                            try:
                                body = await request.body()
                            except:
                                body = None
                    
                    # 记录请求详情
                    request_id = self._monitor_system.record_request_details(
                        method=method,
                        path=request_path,
                        params={},  # 将在路由匹配后填充
                        query=dict(request.query_params),
                        body=body,
                        headers=dict(request.headers),
                        client_ip=get_client_ip(request)
                    )
            
            try:
                # 查找路由
                route_info, path_params = self._router_registry.find_route(method, request_path)
                
                if not route_info:
                    # 路由不存在 - 更新请求状态（仅在DEBUG模式下）
                    if request_id and self._monitor_system and self.debug:
                        duration = time.time() - start_time
                        self._monitor_system.update_request_response(
                            request_id=request_id,
                            status_code=404,
                            response_data={"error": f"Route not found: {request_path}"},
                            duration=duration
                        )
                    return ResponseHandler.not_found_response(request_path)
                
                # 检查限流
                client_ip = get_client_ip(request)
                if self._ratelimit_manager:
                    if not self._ratelimit_manager.check_request(
                        request_path, client_ip, route_info.ratelimit
                    ):
                        if self._monitor_system:
                            self._monitor_system.record_ratelimit_hit()
                            # 更新请求状态为限流（仅在DEBUG模式下）
                            if request_id and self.debug:
                                duration = time.time() - start_time
                                self._monitor_system.update_request_response(
                                    request_id=request_id,
                                    status_code=429,
                                    response_data={"error": "Rate limit exceeded"},
                                    duration=duration
                                )
                        return ResponseHandler.rate_limit_response()
                
                # 检查并发
                if self._concurrent_manager:
                    acquired = await self._concurrent_manager.acquire(timeout=5)
                    if not acquired:
                        # 更新请求状态为服务不可用（仅在DEBUG模式下）
                        if request_id and self._monitor_system and self.debug:
                            duration = time.time() - start_time
                            self._monitor_system.update_request_response(
                                request_id=request_id,
                                status_code=503,
                                response_data={"error": "Service unavailable - too many concurrent requests"},
                                duration=duration
                            )
                        return ResponseHandler.service_unavailable_response()
                else:
                    acquired = False
                
                try:
                    # 检查缓存（仅GET请求）
                    cache_key = None
                    if method == "GET" and self._cache_manager and \
                       (route_info.cache if route_info.cache is not None else self.enable_cache):
                        cache_key = generate_cache_key(method, request_path, dict(request.query_params))
                        cached_response = self._cache_manager.get(cache_key)
                        if cached_response:
                            if self._monitor_system:
                                self._monitor_system.record_cache_hit()
                                # 更新请求状态为缓存命中（仅在DEBUG模式下）
                                if request_id and self.debug:
                                    duration = time.time() - start_time
                                    # 尝试从缓存响应中提取数据
                                    cached_data = None
                                    try:
                                        if hasattr(cached_response, 'content'):
                                            cached_data = cached_response.content
                                        elif hasattr(cached_response, 'body') and cached_response.body:
                                            if isinstance(cached_response.body, bytes):
                                                cached_data = json.loads(cached_response.body.decode('utf-8'))
                                            else:
                                                cached_data = cached_response.body
                                    except Exception as e:
                                        logger.debug(f"Could not extract cached response data: {e}")
                                        cached_data = "<Cached Response>"
                                    
                                    self._monitor_system.update_request_response(
                                        request_id=request_id,
                                        status_code=cached_response.status_code,
                                        response_data=cached_data,
                                        duration=duration
                                    )
                            return cached_response
                        elif self._monitor_system:
                            self._monitor_system.record_cache_miss()
                    
                    # 更新请求的路径参数（仅在DEBUG模式下）
                    if request_id and self._monitor_system and self.debug:
                        for req in self._monitor_system.request_log:
                            if req.get('id') == request_id:
                                req['params'] = path_params
                                break
                    
                    # 处理请求
                    response = await self._request_handler.process_request(
                        request, method, request_path, 
                        route_info.__dict__, path_params
                    )
                    
                    # 记录响应（仅在DEBUG模式下记录详细信息）
                    if request_id and self._monitor_system and self.debug:
                        duration = time.time() - start_time
                        # 获取响应数据
                        response_data = None
                        try:
                            # 检查响应类型并提取内容
                            if hasattr(response, '__class__') and response.__class__.__name__ == 'FormattedJSONResponse':
                                # FormattedJSONResponse 包含content属性
                                if hasattr(response, 'content'):
                                    response_data = response.content
                                    logger.debug(f"Extracted data from FormattedJSONResponse.content: {type(response_data)}")
                                else:
                                    # 如果没有content属性，尝试渲染获取内容
                                    rendered_body = response.render(response.body if hasattr(response, 'body') else {})
                                    if isinstance(rendered_body, bytes):
                                        response_data = json.loads(rendered_body.decode('utf-8'))
                                        logger.debug(f"Rendered and parsed FormattedJSONResponse")
                            elif hasattr(response, 'body'):
                                # 对于其他响应类型，尝试从body获取
                                body = response.body
                                if isinstance(body, bytes):
                                    try:
                                        response_data = json.loads(body.decode('utf-8'))
                                        logger.debug(f"Parsed JSON from response body")
                                    except:
                                        response_data = body.decode('utf-8', errors='ignore')
                                        logger.debug(f"Decoded string from response body")
                                elif body is not None:
                                    response_data = body
                                    logger.debug(f"Got raw body data: {type(body)}")
                            else:
                                logger.debug(f"Response type {type(response)} has no accessible content")
                        except Exception as e:
                            logger.error(f"Failed to extract response data: {e}")
                            response_data = {"error": f"Failed to extract: {str(e)}"}
                        
                        logger.debug(f"Updating response for request_id: {request_id}, status: {response.status_code}, has_data: {response_data is not None}")
                        self._monitor_system.update_request_response(
                            request_id=request_id,
                            status_code=response.status_code,
                            response_data=response_data,
                            duration=duration
                        )
                        logger.debug(f"Response update completed for {request_id}")
                    
                    # 缓存响应
                    if cache_key and response.status_code == 200:
                        self._cache_manager.set(cache_key, response)
                    
                    return response
                    
                finally:
                    if acquired and self._concurrent_manager:
                        self._concurrent_manager.release()
                
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                if self._monitor_system:
                    self._monitor_system.record_error(e, request_path, method)
                    # 更新请求状态为错误（仅在DEBUG模式下）
                    if request_id and self.debug:
                        duration = time.time() - start_time
                        self._monitor_system.update_request_response(
                            request_id=request_id,
                            status_code=500,
                            response_data={"error": str(e)},
                            duration=duration
                        )
                return ResponseHandler.error_response(e, 500)
            
            finally:
                # 记录响应
                duration = time.time() - start_time
                if self._monitor_system:
                    self._monitor_system.record_response(duration)
        
        # 注册所有路由到FastAPI
        for route in self._router_registry.get_routes():
            # 动态路径处理
            fastapi_path = route.path
            
            # 将 {param} 转换为 {param:path} 格式
            import re
            fastapi_path = re.sub(r'\{(\w+)\}', r'{\1:path}', fastapi_path)
            
            # 根据方法注册路由
            if route.method == "GET":
                self._app.get(fastapi_path)(handle_request)
            elif route.method == "POST":
                self._app.post(fastapi_path)(handle_request)
            elif route.method == "PUT":
                self._app.put(fastapi_path)(handle_request)
            elif route.method == "DELETE":
                self._app.delete(fastapi_path)(handle_request)
            elif route.method == "PATCH":
                self._app.patch(fastapi_path)(handle_request)
        
        # 注册通配符路由（捕获所有未匹配的请求）
        self._app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])(handle_request)
    
    def _register_system_routes(self):
        """注册系统路由"""
        
        # 监控面板（仅支持/_debug路径）
        if self.enable_monitor:
            @self._app.get("/_debug", response_class=HTMLResponse)
            async def monitor_page():
                # 准备服务器配置信息
                server_config = {
                    'host': self.host,
                    'port': self.port,
                    'debug': self.debug,
                    'version': self.version,
                    'enable_cors': self.enable_cors,
                    'enable_cache': self.enable_cache,
                    'enable_ratelimit': self.enable_ratelimit,
                    'enable_monitor': self.enable_monitor
                }
                
                # 获取路由统计，包含路由列表
                route_stats = self._router_registry.get_route_stats()
                route_stats['routes'] = [{
                    'method': route.method,
                    'path': route.path,
                    'group': route.group,
                    'name': route.name,
                    'cache': route.cache,
                    'ratelimit': route.ratelimit is not None,
                    'auth': route.auth
                } for route in self._router_registry.get_routes()]
                
                # 获取限流统计
                ratelimit_stats = self._ratelimit_manager.get_stats() if self._ratelimit_manager else {}
                ratelimit_stats['window'] = self.ratelimit_window
                ratelimit_stats['max_requests'] = self.ratelimit_max
                
                html = self._monitor_system.generate_monitor_html(
                    routes_info=route_stats,
                    cache_info=self._cache_manager.get_stats() if self._cache_manager else {},
                    ratelimit_info=ratelimit_stats,
                    concurrent_info=self._concurrent_manager.get_stats() if self._concurrent_manager else {},
                    server_config=server_config
                )
                return HTMLResponse(content=html)
        
        # 健康检查
        if self.enable_health:
            @self._app.get("/_health")
            async def health_check():
                if self._monitor_system:
                    return self._monitor_system.health_check()
                return {"status": "healthy"}
        
        # 路由列表
        @self._app.get("/_routes")
        async def list_routes():
            routes = []
            for route in self._router_registry.get_routes():
                routes.append({
                    "method": route.method,
                    "path": route.path,
                    "group": route.group,
                    "name": route.name
                })
            return {"routes": routes, "total": len(routes)}
        
        # 统计信息
        if self.enable_metrics:
            @self._app.get("/_metrics")
            async def metrics():
                metrics = {}
                
                if self._monitor_system:
                    metrics["server"] = self._monitor_system.get_stats()
                
                if self._cache_manager:
                    metrics["cache"] = self._cache_manager.get_stats()
                
                if self._concurrent_manager:
                    metrics["concurrency"] = self._concurrent_manager.get_stats()
                
                if self._ratelimit_manager:
                    metrics["ratelimit"] = self._ratelimit_manager.get_stats()
                
                metrics["routes"] = self._router_registry.get_route_stats()
                
                return metrics
        
        # Favicon.ico 路由 - 防止404错误
        @self._app.get("/favicon.ico")
        async def favicon():
            """返回默认的 favicon，避免浏览器请求时出现404错误"""
            from fastapi.responses import Response
            # 返回一个简单的透明1x1像素的ICO格式图标
            favicon_data = b'\x00\x00\x01\x00\x01\x00\x01\x01\x00\x00\x01\x00\x18\x00(\x00\x00\x00\x16\x00\x00\x00(\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x01\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x80\x00\x00\x00'
            return Response(content=favicon_data, media_type="image/x-icon", headers={"Cache-Control": "public, max-age=86400"})
        
        # 监控数据API（用于动态更新）
        if self.enable_monitor and self._monitor_system:
            @self._app.get("/_debug/data")
            async def get_monitor_data():
                """获取监控数据的JSON API"""
                data = self._monitor_system.get_monitor_data()
                
                # 添加路由信息
                if "error" not in data:
                    route_stats = self._router_registry.get_route_stats()
                    route_stats['routes'] = [{
                        'method': route.method,
                        'path': route.path,
                        'group': route.group,
                        'name': route.name,
                        'cache': route.cache,
                        'ratelimit': route.ratelimit is not None,
                        'auth': route.auth
                    } for route in self._router_registry.get_routes()]
                    
                    data["routes_info"] = route_stats
                    data["cache_info"] = self._cache_manager.get_stats() if self._cache_manager else {}
                    data["ratelimit_info"] = self._ratelimit_manager.get_stats() if self._ratelimit_manager else {}
                    data["concurrent_info"] = self._concurrent_manager.get_stats() if self._concurrent_manager else {}
                
                return data
            
            @self._app.post("/_debug/clear")
            async def clear_request_log():
                """清空请求日志"""
                if not self.debug:
                    return {"error": "清空功能仅在DEBUG模式下可用"}
                
                self._monitor_system.clear_request_log()
                return {"success": True, "message": "请求日志已清空"}