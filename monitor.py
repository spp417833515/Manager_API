#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控系统模块
提供监控面板、健康检查、指标收集、实时请求日志等功能
"""

import time
import json
from typing import Dict, Any, Optional, List
from collections import deque
from datetime import datetime
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from .types import ServerStats
from .utils import format_duration, format_size
import platform
import logging

# 尝试导入psutil，如果不存在则使用默认值
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logger = logging.getLogger(__name__)


class MonitorSystem:
    """监控系统"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stats = ServerStats()
        self.error_log = deque(maxlen=100)  # 最近的错误日志
        self.request_log = deque(maxlen=500)  # 最近的请求日志
        self.max_request_body_log_size = 10000  # 请求体最大记录大小（增大以显示完整数据）
        self.debug_mode = False  # DEBUG模式标志
    
    def set_debug_mode(self, enabled: bool):
        """设置DEBUG模式"""
        self.debug_mode = enabled
        if enabled:
            logger.info("监控系统DEBUG模式已启用")
    
    def _should_ignore_request(self, path: str) -> bool:
        """判断是否应该忽略该请求"""
        ignore_patterns = [
            # Chrome DevTools requests
            "/.well-known/appspecific/com.chrome.devtools.json",
            # Other common browser/tool requests
            "/favicon.ico",
            "/_debug",
            "/_health", 
            "/_routes",
            "/_metrics",
            # Add more patterns as needed
        ]
        
        for pattern in ignore_patterns:
            if path.startswith(pattern) or path == pattern:
                return True
        
        return False
    
    def record_request_details(self, method: str, path: str, 
                              params: dict = None, query: dict = None, 
                              body: Any = None, headers: dict = None,
                              client_ip: str = None):
        """记录请求详情（仅在DEBUG模式下）"""
        if not self.debug_mode:
            return
        
        # 过滤掉不需要记录的请求
        if self._should_ignore_request(path):
            return
            
        # 准备请求体日志
        body_log = None
        if body:
            try:
                if isinstance(body, (dict, list)):
                    body_str = json.dumps(body, ensure_ascii=False, indent=2)
                else:
                    body_str = str(body)
                
                # 不再截断请求体，保持完整数据
                body_log = body_str
            except:
                body_log = "<无法序列化>"
        
        # 生成唯一的请求ID
        import random
        unique_id = f"req_{int(time.time()*1000000)}_{random.randint(1000000, 9999999)}_{hash(f'{method}{path}{time.time()}')}"
        logger.debug(f"[Monitor] Creating request with ID: {unique_id} for {method} {path}")
        
        # 记录请求
        request_entry = {
            'id': unique_id,
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'method': method,
            'path': path,
            'params': params or {},
            'query': query or {},
            'body': body_log,
            'headers': {k: v for k, v in (headers or {}).items() 
                       if not k.lower().startswith('authorization')},  # 隐藏敏感信息
            'client_ip': client_ip,
            'status': 'pending',
            'response_time': None,
            'response_status': None,
            'response_data': None
        }
        
        self.request_log.append(request_entry)
        logger.debug(f"[Monitor] Recorded new request {unique_id}: {method} {path}")
        return unique_id  # 确保返回请求ID
    
    def update_request_response(self, request_id: str, status_code: int, 
                               response_data: Any = None, duration: float = None):
        """更新请求的响应信息"""
        if not self.debug_mode:
            return
        
        logger.debug(f"Attempting to update request {request_id} with status {status_code}")
            
        # 查找并更新请求
        found = False
        for req in self.request_log:
            if req.get('id') == request_id:
                req['status'] = 'completed'
                req['response_status'] = status_code
                req['response_time'] = duration
                req['completed_at'] = time.time()  # 添加完成时间戳
                
                # 记录响应数据
                if response_data is not None:  # 更改判断条件，允许空字符串等
                    try:
                        if isinstance(response_data, (dict, list)):
                            resp_str = json.dumps(response_data, ensure_ascii=False, indent=2)
                        else:
                            resp_str = str(response_data)
                        
                        # 不再截断响应数据，保持完整数据
                        req['response_data'] = resp_str
                        logger.debug(f"[Monitor] Set response_data for {request_id}, data length: {len(resp_str)}")
                    except Exception as e:
                        req['response_data'] = "<无法序列化>"
                        logger.error(f"[Monitor] Failed to serialize response: {e}")
                else:
                    logger.debug(f"[Monitor] No response_data provided for {request_id}")
                
                found = True
                logger.debug(f"Successfully updated request {request_id}")
                break
        
        if not found:
            logger.warning(f"Failed to find request {request_id} for status update. Current requests: {[r.get('id', 'no-id') for r in self.request_log]}")
    
    def cleanup_stale_requests(self):
        """清理超时的待处理请求"""
        if not self.debug_mode:
            return
        
        current_time = time.time()
        for req in self.request_log:
            if (req.get('status') == 'pending' and 
                current_time - req.get('timestamp', 0) > 30):  # 30秒超时
                req['status'] = 'timeout'
                req['response_status'] = 'TIMEOUT'
                req['response_data'] = '请求超时，可能未被正确处理'
                req['completed_at'] = current_time
    
    def record_request(self):
        """记录请求"""
        self.stats.total_requests += 1
        self.stats.active_requests += 1
    
    def record_response(self, duration: float):
        """记录响应"""
        self.stats.active_requests = max(0, self.stats.active_requests - 1)
        
        # 更新平均响应时间
        if self.stats.average_response_time == 0:
            self.stats.average_response_time = duration
        else:
            # 使用移动平均
            self.stats.average_response_time = (
                self.stats.average_response_time * 0.9 + duration * 0.1
            )
    
    def record_error(self, error: Exception, path: str = "", method: str = ""):
        """记录错误"""
        self.stats.total_errors += 1
        
        # 添加到错误日志
        error_entry = {
            'timestamp': time.time(),
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'path': path,
            'method': method,
            'error': str(error),
            'type': type(error).__name__
        }
        
        self.error_log.append(error_entry)
    
    def record_cache_hit(self):
        """记录缓存命中"""
        self.stats.cache_hits += 1
    
    def record_cache_miss(self):
        """记录缓存未命中"""
        self.stats.cache_misses += 1
    
    def record_ratelimit_hit(self):
        """记录限流触发"""
        self.stats.ratelimit_hits += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.start_time
        self.stats.uptime = uptime
        
        stats_dict = self.stats.to_dict()
        stats_dict['uptime_formatted'] = format_duration(uptime)
        stats_dict['avg_response_time_formatted'] = format_duration(
            self.stats.average_response_time
        )
        
        # 计算缓存命中率
        cache_total = self.stats.cache_hits + self.stats.cache_misses
        if cache_total > 0:
            stats_dict['cache_hit_rate'] = f"{(self.stats.cache_hits / cache_total * 100):.2f}%"
        else:
            stats_dict['cache_hit_rate'] = "N/A"
        
        return stats_dict
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        base_info = {
            'platform': platform.platform(),
            'python_version': platform.python_version()
        }
        
        if not HAS_PSUTIL:
            base_info['note'] = 'Install psutil for system metrics'
            return base_info
            
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            base_info.update({
                'cpu': {
                    'count': psutil.cpu_count(),
                    'usage': f"{cpu_percent}%"
                },
                'memory': {
                    'total': format_size(memory.total),
                    'used': format_size(memory.used),
                    'available': format_size(memory.available),
                    'percent': f"{memory.percent}%"
                },
                'disk': {
                    'total': format_size(disk.total),
                    'used': format_size(disk.used),
                    'free': format_size(disk.free),
                    'percent': f"{disk.percent}%"
                }
            })
            return base_info
        except Exception as e:
            logger.warning(f"Failed to get system info: {e}")
            base_info['error'] = 'Failed to get system metrics'
            return base_info
    
    def get_error_log(self, limit: int = 20) -> List[dict]:
        """获取错误日志"""
        return list(self.error_log)[-limit:]
    
    def get_request_log(self, limit: int = 50) -> List[dict]:
        """获取请求日志"""
        self.cleanup_stale_requests()  # 清理超时请求
        return list(self.request_log)[-limit:]
    
    def clear_request_log(self):
        """清空请求日志"""
        self.request_log.clear()
        logger.info("Request log cleared")
    
    def get_monitor_data(self) -> Dict[str, Any]:
        """获取监控数据（用于API返回）"""
        if not self.debug_mode:
            return {"error": "监控面板仅在DEBUG模式下可用"}
        
        return {
            "stats": self.get_stats(),
            "system_info": self.get_system_info(),
            "errors": self.get_error_log(20),
            "requests": self.get_request_log(50)
        }
    
    def generate_monitor_html(self, 
                            routes_info: Dict[str, Any],
                            cache_info: Dict[str, Any],
                            ratelimit_info: Dict[str, Any],
                            concurrent_info: Dict[str, Any],
                            server_config: Dict[str, Any] = None) -> str:
        """生成现代化监控面板HTML"""
        if not self.debug_mode:
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>监控面板已禁用</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .message {
                        background: white;
                        padding: 40px;
                        border-radius: 15px;
                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                        text-align: center;
                        max-width: 500px;
                    }
                    h1 { 
                        color: #333; 
                        margin-bottom: 20px; 
                        font-size: 2em;
                    }
                    p { 
                        color: #666; 
                        line-height: 1.6;
                        margin: 10px 0;
                    }
                    code { 
                        background: #f5f5f5; 
                        padding: 4px 8px; 
                        border-radius: 4px;
                        color: #d63031;
                        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                    }
                </style>
            </head>
            <body>
                <div class="message">
                    <h1>🔒 监控面板已禁用</h1>
                    <p>监控面板仅在DEBUG模式下可用</p>
                    <p>请设置 <code>server.debug = True</code> 启用监控面板</p>
                </div>
            </body>
            </html>
            """
        
        stats = self.get_stats()
        system_info = self.get_system_info()
        errors = self.get_error_log(20)
        requests = self.get_request_log(50)
        routes_list = routes_info.get('routes', [])
        
        # 分组路由
        grouped_routes = {}
        for route in routes_list:
            group = route.get('group', 'default')
            if group not in grouped_routes:
                grouped_routes[group] = []
            grouped_routes[group].append(route)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>API服务器调试控制台</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <style>
                :root {{
                    --primary-gradient: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                    --secondary-gradient: linear-gradient(135deg, #007bff 0%, #0056b3 100%);
                    --success-gradient: linear-gradient(135deg, #28a745 0%, #1e7e34 100%);
                    --warning-gradient: linear-gradient(135deg, #ffc107 0%, #e0a800 100%);
                    --error-gradient: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                    --card-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
                    --card-hover-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
                    --border-radius: 12px;
                    --text-primary: #212529;
                    --text-secondary: #495057;
                    --text-muted: #6c757d;
                    --bg-light: #ffffff;
                    --bg-white: #ffffff;
                    --bg-dark: #f8f9fa;
                    --accent-primary: #007bff;
                    --accent-secondary: #17a2b8;
                    --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                }}
                
                * {{ 
                    margin: 0; 
                    padding: 0; 
                    box-sizing: border-box; 
                }}
                
                body {{
                    font-family: 'Inter', 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    background: var(--bg-dark);
                    min-height: 100vh;
                    padding: 0;
                    color: var(--text-primary);
                    overflow-x: hidden;
                }}
                
                /* Header */
                .header {{
                    background: var(--bg-white);
                    border-bottom: 1px solid #dee2e6;
                    padding: 20px 0;
                    position: sticky;
                    top: 0;
                    z-index: 100;
                    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                }}
                
                .header-content {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 0 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 20px;
                }}
                
                .header h1 {{
                    color: var(--text-primary);
                    font-size: 2.5rem;
                    font-weight: 700;
                    text-shadow: none;
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                }}
                
                .debug-badge {{
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    background: var(--secondary-gradient);
                    color: white;
                    padding: 8px 16px;
                    border-radius: 8px;
                    font-size: 0.9rem;
                    font-weight: 600;
                    animation: pulse 2s infinite;
                    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
                    border: 1px solid var(--accent-primary);
                }}
                
                .theme-toggle {{
                    background: var(--bg-white);
                    border: 1px solid var(--accent-primary);
                    color: var(--accent-primary);
                    padding: 12px;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: var(--transition);
                    font-size: 1.2rem;
                }}
                
                .theme-toggle:hover {{
                    background: var(--accent-primary);
                    color: white;
                    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
                    transform: scale(1.05);
                }}
                
                @keyframes pulse {{
                    0%, 100% {{ opacity: 1; }}
                    50% {{ opacity: 0.7; }}
                }}
                
                /* Container */
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 30px 20px;
                }}
                
                /* Tabs */
                .tabs {{
                    display: flex;
                    gap: 8px;
                    margin-bottom: 30px;
                    flex-wrap: wrap;
                    background: var(--bg-white);
                    padding: 8px;
                    border-radius: 12px;
                    border: 1px solid #dee2e6;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
                }}
                
                .tab {{
                    background: transparent;
                    color: var(--text-secondary);
                    padding: 12px 24px;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: var(--transition);
                    font-weight: 500;
                    border: 1px solid transparent;
                    font-size: 1rem;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    white-space: nowrap;
                }}
                
                .tab:hover {{
                    background: #f8f9fa;
                    color: var(--text-primary);
                    border: 1px solid #dee2e6;
                    transform: translateY(-1px);
                }}
                
                .tab.active {{
                    background: var(--accent-primary);
                    color: white;
                    border: 1px solid var(--accent-primary);
                    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.3);
                }}
                
                /* Content Areas */
                .content {{
                    display: none;
                    animation: fadeIn 0.5s ease-in-out;
                }}
                
                .content.active {{
                    display: block;
                }}
                
                @keyframes fadeIn {{
                    from {{ opacity: 0; transform: translateY(20px); }}
                    to {{ opacity: 1; transform: translateY(0); }}
                }}
                
                /* Cards */
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                    gap: 25px;
                    margin-bottom: 30px;
                }}
                
                .card {{
                    background: var(--bg-white);
                    border-radius: var(--border-radius);
                    padding: 25px;
                    box-shadow: var(--card-shadow);
                    transition: var(--transition);
                    border: 1px solid #dee2e6;
                }}
                
                .card:hover {{
                    box-shadow: var(--card-hover-shadow);
                    transform: translateY(-2px);
                    border-color: var(--accent-primary);
                }}
                
                .card h2 {{
                    color: var(--text-primary);
                    border-bottom: 2px solid var(--accent-primary);
                    padding-bottom: 15px;
                    margin-bottom: 20px;
                    font-size: 1.3rem;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                
                .stat {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid #e9ecef;
                    transition: var(--transition);
                }}
                
                .stat:last-child {{
                    border-bottom: none;
                }}
                
                .stat:hover {{
                    background: #f8f9fa;
                    margin: 0 -10px;
                    padding: 12px 10px;
                    border-radius: 4px;
                }}
                
                .label {{
                    color: var(--text-secondary);
                    font-weight: 500;
                }}
                
                .value {{
                    font-weight: 600;
                    color: var(--text-primary);
                }}
                
                .success {{ color: #28a745; }}
                .warning {{ color: #ffc107; }}
                .error {{ color: #dc3545; }}
                .info {{ color: #007bff; }}
                
                /* Request Monitoring */
                .request-monitor {{
                    background: var(--bg-white);
                    border-radius: var(--border-radius);
                    padding: 25px;
                    box-shadow: var(--card-shadow);
                    border: 1px solid #dee2e6;
                }}
                
                .bubble-container {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                    gap: 20px;
                    padding: 20px;
                    max-height: 600px;
                    overflow-y: auto;
                }}
                
                .request-bubble {{
                    background: var(--bg-white);
                    color: var(--text-primary);
                    padding: 20px;
                    border-radius: var(--border-radius);
                    cursor: pointer;
                    transition: var(--transition);
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    position: relative;
                    animation: slideIn 0.5s ease-out;
                    border: 1px solid #dee2e6;
                }}
                
                .request-bubble:hover {{
                    transform: translateY(-4px) scale(1.01);
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
                    border-color: var(--accent-primary);
                }}
                
                .bubble-method {{
                    font-weight: 700;
                    font-size: 0.9rem;
                    opacity: 0.9;
                    margin-bottom: 8px;
                }}
                
                .bubble-path {{
                    font-size: 1.1rem;
                    font-weight: 600;
                    margin: 10px 0;
                    word-break: break-all;
                    font-family: 'Courier New', monospace;
                    color: var(--text-primary);
                }}
                
                .bubble-time {{
                    font-size: 0.85rem;
                    opacity: 0.8;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-top: 12px;
                }}
                
                .bubble-status {{
                    position: absolute;
                    top: -8px;
                    right: -8px;
                    width: 32px;
                    height: 32px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 0.8rem;
                    font-weight: 700;
                    color: white;
                    border: 3px solid white;
                }}
                
                .status-success {{ background: #28a745; color: #fff; }}
                .status-error {{ background: #dc3545; color: #fff; }}
                .status-warning {{ background: #ffc107; color: #000; }}
                .status-timeout {{ background: #6f42c1; color: #fff; }}
                .status-pending {{ 
                    background: #6c757d;
                    color: #fff;
                    animation: pulse 1.5s infinite;
                }}
                
                @keyframes slideIn {{
                    from {{
                        opacity: 0;
                        transform: translateY(-30px);
                    }}
                    to {{
                        opacity: 1;
                        transform: translateY(0);
                    }}
                }}
                
                @keyframes fadeOut {{
                    from {{
                        opacity: 1;
                        transform: translateY(0);
                    }}
                    to {{
                        opacity: 0;
                        transform: translateY(-10px);
                    }}
                }}
                
                /* Modal */
                .request-modal {{
                    display: none;
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.8);
                    backdrop-filter: blur(5px);
                    z-index: 1000;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                }}
                
                .modal-content {{
                    background: var(--bg-white);
                    border-radius: var(--border-radius);
                    padding: 30px;
                    max-width: 900px;
                    max-height: 90vh;
                    overflow-y: auto;
                    position: relative;
                    box-shadow: 0 0 30px rgba(59, 130, 246, 0.3);
                    animation: modalIn 0.3s ease-out;
                    border: 2px solid var(--accent-primary);
                }}
                
                @keyframes modalIn {{
                    from {{
                        opacity: 0;
                        transform: scale(0.9) translateY(-20px);
                    }}
                    to {{
                        opacity: 1;
                        transform: scale(1) translateY(0);
                    }}
                }}
                
                .modal-close {{
                    position: absolute;
                    top: 15px;
                    right: 15px;
                    background: none;
                    border: none;
                    font-size: 2rem;
                    cursor: pointer;
                    color: var(--text-muted);
                    transition: var(--transition);
                    width: 40px;
                    height: 40px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    border-radius: 50%;
                }}
                
                .modal-close:hover {{
                    color: var(--text-primary);
                    background: var(--bg-light);
                }}
                
                /* API Routes */
                .route-groups {{
                    display: grid;
                    gap: 25px;
                }}
                
                .route-group {{
                    background: var(--bg-white);
                    border-radius: var(--border-radius);
                    padding: 25px;
                    box-shadow: var(--card-shadow);
                }}
                
                .route-group h3 {{
                    color: var(--text-primary);
                    font-size: 1.4rem;
                    font-weight: 600;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e2e8f0;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                }}
                
                .route-item {{
                    display: grid;
                    grid-template-columns: auto 1fr auto auto auto;
                    gap: 15px;
                    align-items: center;
                    padding: 15px;
                    margin: 10px 0;
                    background: var(--bg-light);
                    border-radius: 10px;
                    transition: var(--transition);
                }}
                
                .route-item:hover {{
                    background: #e2e8f0;
                    transform: translateX(5px);
                }}
                
                .method-badge {{
                    font-weight: 700;
                    padding: 6px 12px;
                    border-radius: 6px;
                    color: white;
                    font-size: 0.85rem;
                    min-width: 70px;
                    text-align: center;
                }}
                
                .method-GET {{ background: var(--success-gradient); }}
                .method-POST {{ background: var(--primary-gradient); }}
                .method-PUT {{ background: var(--warning-gradient); }}
                .method-DELETE {{ background: var(--error-gradient); }}
                .method-PATCH {{ background: var(--secondary-gradient); }}
                
                .route-path {{
                    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                    color: var(--text-primary);
                    font-weight: 600;
                    font-size: 1rem;
                }}
                
                .feature-badge {{
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    display: inline-flex;
                    align-items: center;
                    gap: 4px;
                }}
                
                .feature-enabled {{
                    background: #dcfce7;
                    color: #15803d;
                }}
                
                .feature-disabled {{
                    background: #fef2f2;
                    color: #dc2626;
                }}
                
                /* Error Log */
                .error-log {{
                    max-height: 500px;
                    overflow-y: auto;
                }}
                
                .error-item {{
                    padding: 20px;
                    margin: 15px 0;
                    background: linear-gradient(135deg, #fef2f2 0%, #fde8e8 100%);
                    border-left: 5px solid #ef4444;
                    border-radius: 10px;
                    transition: var(--transition);
                }}
                
                .error-item:hover {{
                    transform: translateX(5px);
                    box-shadow: 0 5px 15px rgba(239, 68, 68, 0.1);
                }}
                
                .error-header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 10px;
                }}
                
                .error-type {{
                    font-weight: 700;
                    color: #dc2626;
                    font-size: 1.1rem;
                }}
                
                .error-time {{
                    color: var(--text-muted);
                    font-size: 0.9rem;
                }}
                
                .error-details {{
                    font-family: 'Monaco', monospace;
                    font-size: 0.9rem;
                    color: #991b1b;
                    background: rgba(255,255,255,0.7);
                    padding: 15px;
                    border-radius: 8px;
                    margin-top: 10px;
                    word-break: break-all;
                }}
                
                /* Empty State */
                .empty-state {{
                    text-align: center;
                    padding: 60px 20px;
                    color: var(--text-muted);
                }}
                
                .empty-state i {{
                    font-size: 3rem;
                    margin-bottom: 20px;
                    opacity: 0.5;
                }}
                
                .empty-state h3 {{
                    font-size: 1.3rem;
                    margin-bottom: 10px;
                    color: var(--text-secondary);
                }}
                
                /* Responsive */
                @media (max-width: 768px) {{
                    .header-content {{
                        flex-direction: column;
                        text-align: center;
                    }}
                    
                    .header h1 {{
                        font-size: 2rem;
                    }}
                    
                    .tabs {{
                        overflow-x: auto;
                        flex-wrap: nowrap;
                    }}
                    
                    .tab {{
                        min-width: 120px;
                    }}
                    
                    .grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .bubble-container {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .route-item {{
                        grid-template-columns: 1fr;
                        gap: 10px;
                    }}
                }}
                
                /* Dark mode styles - True dark theme */
                body.dark {{
                    --bg-dark: #0d1117;
                    --bg-white: #161b22;
                    --bg-light: #1a1d23;
                    --text-primary: #c9d1d9;
                    --text-secondary: #8b949e;
                    --text-muted: #6e7681;
                    --accent-primary: #58a6ff;
                    --accent-secondary: #39d353;
                    --card-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                    --card-hover-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
                    --border-radius: 12px;
                }}
                
                body.dark .header {{
                    background: var(--bg-white);
                    border-bottom: 1px solid #30363d;
                    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
                }}
                
                body.dark .tabs {{
                    background: var(--bg-white);
                    border: 1px solid #30363d;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
                }}
                
                body.dark .tab {{
                    color: var(--text-secondary);
                    border: 1px solid transparent;
                }}
                
                body.dark .tab:hover {{
                    background: #21262d;
                    color: var(--text-primary);
                    border: 1px solid #30363d;
                }}
                
                body.dark .tab.active {{
                    background: var(--accent-primary);
                    color: #ffffff;
                    border: 1px solid var(--accent-primary);
                    box-shadow: 0 2px 8px rgba(88, 166, 255, 0.3);
                }}
                
                body.dark .card {{
                    background: var(--bg-white);
                    border: 1px solid #30363d;
                    box-shadow: var(--card-shadow);
                }}
                
                body.dark .card:hover {{
                    box-shadow: var(--card-hover-shadow);
                    border-color: var(--accent-primary);
                }}
                
                body.dark .card h2 {{
                    color: var(--text-primary);
                    border-bottom: 2px solid var(--accent-primary);
                }}
                
                body.dark .stat {{
                    border-bottom: 1px solid #30363d;
                }}
                
                body.dark .stat:hover {{
                    background: #21262d;
                }}
                
                body.dark .label {{
                    color: var(--text-secondary);
                }}
                
                body.dark .value {{
                    color: var(--text-primary);
                }}
                
                body.dark .route-group {{
                    background: var(--bg-white);
                    border: 1px solid #30363d;
                    box-shadow: var(--card-shadow);
                }}
                
                body.dark .route-item {{
                    background: var(--bg-light);
                    border: 1px solid #30363d;
                }}
                
                body.dark .route-item:hover {{
                    background: #21262d;
                    border-color: var(--accent-primary);
                }}
                
                body.dark .request-monitor {{
                    background: var(--bg-white);
                    border: 1px solid #30363d;
                    box-shadow: var(--card-shadow);
                }}
                
                body.dark .bubble-container {{
                    background: var(--bg-light);
                }}
                
                body.dark .request-bubble {{
                    background: var(--bg-white);
                    color: var(--text-primary);
                    border: 1px solid #30363d;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
                }}
                
                body.dark .request-bubble:hover {{
                    border-color: var(--accent-primary);
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
                }}
                
                body.dark .bubble-path {{
                    color: var(--text-primary);
                }}
                
                body.dark .modal-content {{
                    background: var(--bg-white);
                    border: 2px solid var(--accent-primary);
                    box-shadow: 0 0 30px rgba(88, 166, 255, 0.3);
                }}
                
                body.dark .modal-close:hover {{
                    background: var(--bg-light);
                    color: var(--text-primary);
                }}
                
                body.dark .error-item {{
                    background: linear-gradient(135deg, #2d1b1b 0%, #3d1a1a 100%);
                    border-left: 5px solid #f85149;
                }}
                
                body.dark .error-details {{
                    background: rgba(0, 0, 0, 0.3);
                    color: #ffa198;
                }}
                
                body.dark pre {{
                    background: #21262d !important;
                    color: #c9d1d9 !important;
                    border: 1px solid #30363d;
                }}
                
                body.dark .modal-content pre {{
                    background: #161b22 !important;
                    color: #c9d1d9 !important;
                    border: 1px solid #30363d;
                    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
                }}
                
                /* Fix for modal body response section background in dark mode */
                body.dark .modal-response-section {{
                    background: linear-gradient(135deg, #1a2332 0%, #243447 100%) !important;
                }}
                
                body.dark .modal-response-section pre {{
                    background: #0d1117 !important;
                    color: #c9d1d9 !important;
                    border: 1px solid #30363d;
                }}
                
                body.dark .empty-state {{
                    color: var(--text-muted);
                }}
                
                body.dark .empty-state h3 {{
                    color: var(--text-secondary);
                }}
                
                body.dark .theme-toggle {{
                    background: var(--bg-white);
                    border: 1px solid var(--accent-primary);
                    color: var(--accent-primary);
                }}
                
                body.dark .theme-toggle:hover {{
                    background: var(--accent-primary);
                    color: #ffffff;
                }}
                
                body.dark .debug-badge {{
                    background: linear-gradient(135deg, var(--accent-primary) 0%, #1f6feb 100%);
                    box-shadow: 0 2px 8px rgba(88, 166, 255, 0.3);
                    border: 1px solid var(--accent-primary);
                }}
            </style>
            <script>
                // Language support
                let currentLang = localStorage.getItem('language') || 'zh';
                
                const translations = {{
                    zh: {{
                        title: 'API调试控制台',
                        debugMode: '调试模式',
                        realTimeMonitor: '实时监控',
                        apiRoutes: 'API路由',
                        serverStatus: '服务器状态',
                        liveRequestStream: '实时请求流',
                        recent: '最新',
                        clearLog: '清空日志',
                        noRequests: '还没有请求',
                        requestsWillAppear: '请求到达时将显示在这里',
                        serverStats: '服务器统计',
                        cacheStatus: '缓存状态',
                        systemInfo: '系统信息',
                        requestLimits: '请求限制',
                        runtime: '运行时间',
                        totalRequests: '总请求数',
                        activeRequests: '活跃请求',
                        errorCount: '错误数',
                        avgResponseTime: '平均响应时间',
                        enabled: '已启用',
                        size: '大小',
                        hitRate: '命中率',
                        hits: '命中',
                        misses: '未命中',
                        cpuUsage: 'CPU使用率',
                        memoryUsage: '内存使用率',
                        diskUsage: '磁盘使用率',
                        pythonVersion: 'Python版本',
                        timeWindow: '时间窗口',
                        maxRequests: '最大请求数',
                        blocked: '被阻止',
                        requestDetails: '请求详情',
                        processing: '请求正在处理中...',
                        responseTime: '响应时间',
                        requestPayload: '请求数据',
                        responseData: '响应数据',
                        requestHeaders: '请求头',
                        clientIP: '客户端IP',
                        close: '关闭',
                        logCleared: '请求日志已清空',
                        clearFailed: '清空失败',
                        group: '分组',
                        name: '名称',
                        cache: '缓存',
                        rateLimit: '限流',
                        enabled: '启用',
                        disabled: '禁用',
                        serverInfo: '服务器信息',
                        host: '主机',
                        port: '端口',
                        version: '版本',
                        uptime: '运行时间',
                        totalRequests: '总请求数',
                        activeRequests: '活跃请求',
                        avgResponseTime: '平均响应时间',
                        cacheHitRate: '缓存命中率',
                        errorRate: '错误率',
                        recentErrors: '最近错误',
                        noErrors: '没有错误记录',
                        serverRunning: '您的服务器运行正常！',
                        language: '语言',
                        theme: '主题'
                    }},
                    en: {{
                        title: 'API Debug Console',
                        debugMode: 'Debug Mode',
                        realTimeMonitor: 'Real-time Monitor',
                        apiRoutes: 'API Routes',
                        serverStatus: 'Server Status',
                        liveRequestStream: 'Live Request Stream',
                        recent: 'recent',
                        clearLog: 'Clear Log',
                        noRequests: 'No requests yet',
                        requestsWillAppear: 'Requests will appear here as they come in',
                        serverStats: 'Server Statistics',
                        cacheStatus: 'Cache Status',
                        systemInfo: 'System Information',
                        requestLimits: 'Request Limits',
                        runtime: 'Runtime',
                        totalRequests: 'Total Requests',
                        activeRequests: 'Active Requests',
                        errorCount: 'Error Count',
                        avgResponseTime: 'Avg Response Time',
                        enabled: 'Enabled',
                        size: 'Size',
                        hitRate: 'Hit Rate',
                        hits: 'Hits',
                        misses: 'Misses',
                        cpuUsage: 'CPU Usage',
                        memoryUsage: 'Memory Usage',
                        diskUsage: 'Disk Usage',
                        pythonVersion: 'Python Version',
                        timeWindow: 'Time Window',
                        maxRequests: 'Max Requests',
                        blocked: 'Blocked',
                        requestDetails: 'Request Details',
                        processing: 'Request is being processed...',
                        responseTime: 'Response Time',
                        requestPayload: 'Request Payload',
                        responseData: 'Response Data',
                        requestHeaders: 'Request Headers',
                        clientIP: 'Client IP',
                        close: 'Close',
                        logCleared: 'Request log cleared',
                        clearFailed: 'Clear failed',
                        group: 'Group',
                        name: 'Name',
                        cache: 'Cache',
                        rateLimit: 'Rate Limit',
                        enabled: 'Enabled',
                        disabled: 'Disabled',
                        serverInfo: 'Server Info',
                        host: 'Host',
                        port: 'Port',
                        version: 'Version',
                        uptime: 'Uptime',
                        totalRequests: 'Total Requests',
                        activeRequests: 'Active Requests',
                        avgResponseTime: 'Avg Response Time',
                        cacheHitRate: 'Cache Hit Rate',
                        errorRate: 'Error Rate',
                        recentErrors: 'Recent Errors',
                        noErrors: 'No error records',
                        serverRunning: 'Your server is running smoothly!',
                        language: 'Language',
                        theme: 'Theme'
                    }}
                }};
                
                function t(key) {{
                    return translations[currentLang][key] || key;
                }}
                
                function toggleLanguage() {{
                    currentLang = currentLang === 'zh' ? 'en' : 'zh';
                    localStorage.setItem('language', currentLang);
                    updateLanguage();
                }}
                
                function updateLanguage() {{
                    // Update all text content with data-i18n attribute
                    document.querySelectorAll('[data-i18n]').forEach(elem => {{
                        const key = elem.getAttribute('data-i18n');
                        elem.textContent = t(key);
                    }});
                    
                    // Update placeholders and titles
                    document.querySelectorAll('[data-i18n-title]').forEach(elem => {{
                        const key = elem.getAttribute('data-i18n-title');
                        elem.title = t(key);
                    }});
                }}
                
                // Theme toggle
                function toggleTheme() {{
                    document.body.classList.toggle('dark');
                    const isDark = document.body.classList.contains('dark');
                    localStorage.setItem('theme', isDark ? 'dark' : 'light');
                    document.querySelector('.theme-toggle i').className = 
                        isDark ? 'fas fa-sun' : 'fas fa-moon';
                }}
                
                // Load theme
                window.addEventListener('load', () => {{
                    const savedTheme = localStorage.getItem('theme');
                    if (savedTheme === 'dark') {{
                        document.body.classList.add('dark');
                        document.querySelector('.theme-toggle i').className = 'fas fa-sun';
                    }}
                    
                    const currentTab = localStorage.getItem('currentTab') || 'monitor';
                    switchTab(currentTab);
                }});
                
                // Tab switching
                function switchTab(tabName) {{
                    const tabs = document.querySelectorAll('.tab');
                    const contents = document.querySelectorAll('.content');
                    
                    tabs.forEach(tab => {{
                        if (tab.dataset.tab === tabName) {{
                            tab.classList.add('active');
                        }} else {{
                            tab.classList.remove('active');
                        }}
                    }});
                    
                    contents.forEach(content => {{
                        if (content.id === tabName) {{
                            content.classList.add('active');
                        }} else {{
                            content.classList.remove('active');
                        }}
                    }});
                }}
                
                // Removed duplicate - see enhanced setTab function below
                
                // Request details
                const requestsData = {json.dumps([req for req in requests], ensure_ascii=False, indent=2) if requests else '[]'};
                
                // Format JSON response data for better readability
                function formatJsonResponse(data) {{
                    if (!data) return '';
                    
                    try {{
                        // Try to parse as JSON first
                        const parsed = JSON.parse(data);
                        return JSON.stringify(parsed, null, 2);
                    }} catch (e) {{
                        // If not valid JSON, try to detect if it looks like JSON and format it
                        const trimmed = data.trim();
                        if ((trimmed.startsWith('{{') && trimmed.endsWith('}}')) || 
                            (trimmed.startsWith('[') && trimmed.endsWith(']'))) {{
                            try {{
                                const parsed = JSON.parse(trimmed);
                                return JSON.stringify(parsed, null, 2);
                            }} catch (e2) {{
                                // Still not valid JSON, return as is
                                return data;
                            }}
                        }}
                        // Return original data if not JSON-like
                        return data;
                    }}
                }}
                
                function showRequestDetail(requestId) {{
                    const request = requestsData.find(r => r.id === requestId);
                    if (!request) return;
                    
                    const modal = document.getElementById('requestModal');
                    const modalBody = document.getElementById('modalBody');
                    
                    let statusClass = 'info';
                    if (request.response_status !== null && request.response_status !== undefined) {{
                        if (request.response_status >= 200 && request.response_status < 300) {{
                            statusClass = 'success';
                        }} else if (request.response_status >= 400 && request.response_status < 500) {{
                            statusClass = 'warning';
                        }} else if (request.response_status >= 500) {{
                            statusClass = 'error';
                        }}
                    }}
                    
                    modalBody.innerHTML = `
                        <h2 style="margin-bottom: 25px; font-size: 1.8rem;">
                            <i class="fas fa-info-circle"></i> 请求详情
                        </h2>
                        <div style="background: var(--bg-light); padding: 20px; border-radius: 12px; margin-bottom: 25px;">
                            <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                                <span class="method-badge method-${{request.method}}">${{request.method}}</span>
                                <span style="font-family: monospace; font-size: 1.3rem; font-weight: 600;">${{request.path}}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; font-size: 0.95rem;">
                                <div><i class="fas fa-clock"></i> ${{request.datetime}}</div>
                                <div><i class="fas fa-globe"></i> ${{request.client_ip || 'unknown'}}</div>
                                <div><i class="fas fa-fingerprint"></i> ${{request.id}}</div>
                                ${{request.response_time ? `<div><i class="fas fa-tachometer-alt"></i> ${{(request.response_time * 1000).toFixed(2)}}ms</div>` : ''}}
                            </div>
                        </div>
                        
                        ${{Object.keys(request.params || {{}}).length > 0 ? 
                            `<div style="margin-bottom: 25px;">
                                <h4 style="margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <i class="fas fa-route"></i> 路径参数
                                </h4>
                                <pre style="background: var(--bg-light); color: var(--text-primary); padding: 15px; border-radius: 8px; overflow-x: auto; font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 0.9rem; line-height: 1.4; border: 1px solid var(--text-muted); white-space: pre-wrap; word-wrap: break-word;">${{JSON.stringify(request.params, null, 2)}}</pre>
                            </div>` : ''}}
                        
                        ${{Object.keys(request.query || {{}}).length > 0 ? 
                            `<div style="margin-bottom: 25px;">
                                <h4 style="margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <i class="fas fa-search"></i> 查询参数
                                </h4>
                                <pre style="background: var(--bg-light); color: var(--text-primary); padding: 15px; border-radius: 8px; overflow-x: auto; font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 0.9rem; line-height: 1.4; border: 1px solid var(--text-muted); white-space: pre-wrap; word-wrap: break-word;">${{JSON.stringify(request.query, null, 2)}}</pre>
                            </div>` : ''}}
                        
                        ${{request.body ? 
                            `<div style="margin-bottom: 25px;">
                                <h4 style="margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                                    <i class="fas fa-file-code"></i> 请求体
                                </h4>
                                <pre style="background: var(--bg-light); color: var(--text-primary); padding: 15px; border-radius: 8px; max-height: 300px; overflow-y: auto; font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 0.9rem; line-height: 1.4; border: 1px solid var(--text-muted); white-space: pre-wrap; word-wrap: break-word;">${{formatJsonResponse(request.body)}}</pre>
                            </div>` : ''}}
                        
                        ${{request.status === 'completed' || request.status === 'timeout' ? `
                            <div class="modal-response-section" style="background: linear-gradient(135deg, #f0f8ff 0%, #e6f3ff 100%); padding: 20px; border-radius: 12px;">
                                <h4 style="margin-bottom: 15px; display: flex; align-items: center; gap: 8px; color: var(--text-primary);">
                                    <i class="fas fa-reply"></i> 响应信息
                                </h4>
                                <div style="display: flex; gap: 20px; margin-bottom: 15px; flex-wrap: wrap;">
                                    <div style="color: var(--text-primary);">状态: <span class="${{statusClass}}" style="font-weight: 700;">${{request.response_status}}</span></div>
                                    <div style="color: var(--text-primary);">时间: <strong>${{(request.response_time * 1000).toFixed(2)}}ms</strong></div>
                                </div>
                                ${{request.response_data ? 
                                    `<div>
                                        <strong style="color: var(--text-primary);">响应数据:</strong>
                                        <pre style="background: var(--bg-white); color: var(--text-primary); padding: 15px; border-radius: 8px; margin-top: 10px; max-height: 300px; overflow-y: auto; font-family: 'Monaco', 'Menlo', 'Consolas', monospace; font-size: 0.9rem; line-height: 1.4; border: 1px solid var(--text-muted); white-space: pre-wrap; word-wrap: break-word;">${{formatJsonResponse(request.response_data)}}</pre>
                                    </div>` : ''}}
                            </div>
                        ` : `
                            <div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b3 100%); padding: 20px; border-radius: 12px; text-align: center;">
                                <i class="fas fa-spinner fa-spin" style="font-size: 1.5rem; margin-bottom: 10px;"></i>
                                <div style="color: #f57c00; font-weight: 600;">请求正在处理中...</div>
                            </div>
                        `}}
                    `;
                    
                    modal.style.display = 'flex';
                }}
                
                function closeModal(event) {{
                    if (!event || event.target.id === 'requestModal' || event.target.className === 'modal-close') {{
                        document.getElementById('requestModal').style.display = 'none';
                    }}
                }}
                
                // Keyboard shortcuts
                document.addEventListener('keydown', function(event) {{
                    if (event.key === 'Escape') {{
                        closeModal();
                    }}
                    if (event.ctrlKey || event.metaKey) {{
                        if (event.key === 'd') {{
                            event.preventDefault();
                            toggleTheme();
                        }}
                    }}
                }});
                
                // 动态更新数据变量
                let lastUpdateTime = 0;
                let isUpdating = false;
                
                // 动态更新监控数据
                async function updateMonitorData() {{
                    if (isUpdating) return;
                    isUpdating = true;
                    
                    try {{
                        const response = await fetch('/_debug/data');
                        if (!response.ok) throw new Error('获取数据失败');
                        
                        const data = await response.json();
                        
                        if (data.error) {{
                            console.warn(data.error);
                            return;
                        }}
                        
                        // 更新请求日志（保持用户状态）
                        await updateRequestBubbles(data.requests || []);
                        
                        // 更新统计数据
                        updateStats(data.stats || {{}});
                        
                        // 更新系统信息
                        updateSystemInfo(data.system_info || {{}});
                        
                        lastUpdateTime = Date.now();
                    }} catch (error) {{
                        console.error('更新监控数据失败:', error);
                    }} finally {{
                        isUpdating = false;
                    }}
                }}
                
                // 更新请求气泡
                async function updateRequestBubbles(newRequests) {{
                    const container = document.querySelector('.bubble-container');
                    if (!container) return;
                    
                    // 检查是否有新请求
                    const existingIds = Array.from(container.children).map(el => 
                        el.getAttribute('onclick')?.match(/'([^']+)'/)?.[1]
                    ).filter(Boolean);
                    
                    let hasNewRequests = false;
                    const newBubbles = [];
                    
                    newRequests.reverse().forEach(req => {{
                        if (!existingIds.includes(req.id)) {{
                            hasNewRequests = true;
                            let statusClass = 'pending';
                            if (req.status === 'timeout') {{
                                statusClass = 'timeout';
                            }} else if (req.response_status !== null && req.response_status !== undefined) {{
                                if (req.response_status >= 200 && req.response_status < 300) {{
                                    statusClass = 'success';
                                }} else if (req.response_status >= 400 && req.response_status < 500) {{
                                    statusClass = 'warning';
                                }} else if (req.response_status >= 500) {{
                                    statusClass = 'error';
                                }}
                            }}
                            
                            const bubble = document.createElement('div');
                            bubble.className = 'request-bubble';
                            bubble.setAttribute('onclick', `showRequestDetail('${{req.id}}')`);
                            bubble.style.animation = 'slideIn 0.5s ease-out';
                            
                            bubble.innerHTML = `
                                <div class="bubble-status status-${{statusClass}}">
                                    ${{statusClass === 'timeout' ? '⏱' : (req.response_status ?? '⋯')}}
                                </div>
                                <div class="bubble-method">${{req.method}}</div>
                                <div class="bubble-path">${{req.path.length > 40 ? req.path.substring(0, 40) + '...' : req.path}}</div>
                                <div class="bubble-time">
                                    <span>${{req.datetime.split(' ')[1] || req.datetime}}</span>
                                    <span>${{req.response_time ? (req.response_time * 1000).toFixed(0) + 'ms' : ''}}</span>
                                </div>
                            `;
                            
                            newBubbles.push(bubble);
                        }}
                    }});
                    
                    // 添加新的请求气泡到顶部
                    if (hasNewRequests) {{
                        newBubbles.forEach(bubble => {{
                            if (container.firstChild && container.firstChild.className !== 'empty-state') {{
                                container.insertBefore(bubble, container.firstChild);
                            }} else {{
                                // 移除空状态提示
                                if (container.firstChild?.className === 'empty-state') {{
                                    container.removeChild(container.firstChild);
                                }}
                                container.appendChild(bubble);
                            }}
                        }});
                        
                        // 更新全局请求数据
                        requestsData.splice(0, 0, ...newRequests.filter(req => !requestsData.find(r => r.id === req.id)));
                        
                        // 更新标题中的请求数量
                        const titleElement = document.querySelector('#monitor h2');
                        if (titleElement) {{
                            const newCount = newRequests.length;
                            titleElement.innerHTML = `
                                <i class="fas fa-comments"></i>
                                Live Request Stream (${{newCount}} recent)
                            `;
                        }}
                    }}
                }}
                
                // 更新统计数据
                function updateStats(stats) {{
                    const updateStat = (selector, value) => {{
                        const element = document.querySelector(selector);
                        if (element) element.textContent = value;
                    }};
                    
                    updateStat('[data-stat="uptime"]', stats.uptime_formatted || '0s');
                    updateStat('[data-stat="total_requests"]', stats.total_requests || 0);
                    updateStat('[data-stat="active_requests"]', stats.active_requests || 0);
                    updateStat('[data-stat="total_errors"]', stats.total_errors || 0);
                    updateStat('[data-stat="avg_response_time"]', stats.avg_response_time_formatted || '0ms');
                    updateStat('[data-stat="cache_hit_rate"]', stats.cache_hit_rate || 'N/A');
                    updateStat('[data-stat="cache_hits"]', stats.cache_hits || 0);
                    updateStat('[data-stat="cache_misses"]', stats.cache_misses || 0);
                    updateStat('[data-stat="ratelimit_hits"]', stats.ratelimit_hits || 0);
                }}
                
                // 更新系统信息
                function updateSystemInfo(systemInfo) {{
                    const updateStat = (selector, value) => {{
                        const element = document.querySelector(selector);
                        if (element) element.textContent = value;
                    }};
                    
                    updateStat('[data-stat="cpu_usage"]', systemInfo.cpu?.usage || 'N/A');
                    updateStat('[data-stat="memory_percent"]', systemInfo.memory?.percent || 'N/A');
                    updateStat('[data-stat="disk_percent"]', systemInfo.disk?.percent || 'N/A');
                }}
                
                // 清空请求日志
                async function clearRequestLog() {{
                    if (!confirm('确定要清空所有请求日志吗？')) return;
                    
                    try {{
                        const response = await fetch('/_debug/clear', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/json'
                            }}
                        }});
                        
                        if (!response.ok) throw new Error('清空失败');
                        
                        const result = await response.json();
                        
                        if (result.success) {{
                            // 清空页面上的请求气泡
                            const container = document.querySelector('.bubble-container');
                            if (container) {{
                                container.innerHTML = `
                                    <div class="empty-state">
                                        <i class="fas fa-inbox"></i>
                                        <h3>No requests yet</h3>
                                        <p>Requests will appear here as they come in</p>
                                    </div>
                                `;
                            }}
                            
                            // 清空全局数据
                            requestsData.length = 0;
                            
                            // 更新标题
                            const titleElement = document.querySelector('#monitor h2');
                            if (titleElement) {{
                                titleElement.innerHTML = `
                                    <i class="fas fa-comments"></i>
                                    Live Request Stream (0 recent)
                                `;
                            }}
                            
                            // 显示成功消息
                            showNotification(t('logCleared'), 'success');
                        }} else {{
                            throw new Error(result.error || 'Unknown error');
                        }}
                    }} catch (error) {{
                        console.error('Clear request log failed:', error);
                        showNotification(t('clearFailed') + ': ' + error.message, 'error');
                    }}
                }}
                
                // 显示通知
                function showNotification(message, type = 'info') {{
                    const notification = document.createElement('div');
                    notification.className = `notification notification-${{type}}`;
                    notification.textContent = message;
                    notification.style.cssText = `
                        position: fixed;
                        top: 20px;
                        right: 20px;
                        padding: 12px 20px;
                        border-radius: 8px;
                        color: white;
                        font-weight: 600;
                        z-index: 10000;
                        animation: slideIn 0.3s ease-out;
                        background: ${{type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'}};
                    `;
                    
                    document.body.appendChild(notification);
                    
                    setTimeout(() => {{
                        notification.style.animation = 'fadeOut 0.3s ease-out forwards';
                        setTimeout(() => {{
                            document.body.removeChild(notification);
                        }}, 300);
                    }}, 3000);
                }}
                
                // 智能轮询：根据活动情况调整频率
                let pollInterval = null;
                let consecutiveEmptyUpdates = 0;
                let currentPollDelay = 5000; // 开始5秒间隔
                const maxPollDelay = 30000; // 最大30秒间隔
                const minPollDelay = 3000; // 最小3秒间隔
                
                function startSmartPolling() {{
                    if (pollInterval) clearInterval(pollInterval);
                    
                    pollInterval = setInterval(async () => {{
                        // 仅在页面可见且在监控标签时才轮询
                        if (document.visibilityState === 'visible' && 
                            document.querySelector('.tab[data-tab="monitor"]').classList.contains('active')) {{
                            
                            const previousRequestCount = requestsData.length;
                            await updateMonitorData();
                            const currentRequestCount = requestsData.length;
                            
                            // 如果有新请求，减少轮询间隔
                            if (currentRequestCount > previousRequestCount) {{
                                consecutiveEmptyUpdates = 0;
                                currentPollDelay = Math.max(minPollDelay, currentPollDelay * 0.8);
                            }} else {{
                                // 没有新请求，增加轮询间隔
                                consecutiveEmptyUpdates++;
                                if (consecutiveEmptyUpdates >= 3) {{
                                    currentPollDelay = Math.min(maxPollDelay, currentPollDelay * 1.5);
                                }}
                            }}
                            
                            // 重新设置间隔
                            if (pollInterval) {{
                                clearInterval(pollInterval);
                                startSmartPolling();
                            }}
                        }}
                    }}, currentPollDelay);
                }}
                
                // 页面可见性变化时调整轮询
                document.addEventListener('visibilitychange', () => {{
                    if (document.visibilityState === 'visible') {{
                        consecutiveEmptyUpdates = 0;
                        currentPollDelay = minPollDelay;
                        startSmartPolling();
                    }} else {{
                        if (pollInterval) {{
                            clearInterval(pollInterval);
                            pollInterval = null;
                        }}
                    }}
                }});
                
                // 标签切换时调整轮询
                function setTab(tabName) {{
                    localStorage.setItem('currentTab', tabName);
                    switchTab(tabName);
                    
                    // 只在监控标签时启用轮询
                    if (tabName === 'monitor') {{
                        if (!pollInterval && document.visibilityState === 'visible') {{
                            consecutiveEmptyUpdates = 0;
                            currentPollDelay = minPollDelay;
                            startSmartPolling();
                        }}
                    }} else {{
                        if (pollInterval) {{
                            clearInterval(pollInterval);
                            pollInterval = null;
                        }}
                    }}
                }}
                
                // 启动智能轮询
                startSmartPolling();
                
                // 页面加载完成后立即更新一次数据
                window.addEventListener('load', () => {{
                    updateLanguage();
                    setTimeout(updateMonitorData, 1000);
                }});
            </script>
        </head>
        <body>
            <header class="header">
                <div class="header-content">
                    <h1>
                        <i class="fas fa-rocket"></i>
                        <span data-i18n="title">API调试控制台</span>
                    </h1>
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <span class="debug-badge">
                            <i class="fas fa-bug"></i>
                            <span data-i18n="debugMode">调试模式</span>
                        </span>
                        <button class="theme-toggle" onclick="toggleLanguage()" title="Switch Language" style="background: var(--accent-primary); color: white;">
                            <i class="fas fa-globe"></i>
                        </button>
                        <button class="theme-toggle" onclick="toggleTheme()" data-i18n-title="theme">
                            <i class="fas fa-moon"></i>
                        </button>
                    </div>
                </div>
            </header>
            
            <div class="container">
                <div class="tabs">
                    <button class="tab active" data-tab="monitor" onclick="setTab('monitor')">
                        <i class="fas fa-chart-line"></i>
                        <span data-i18n="realTimeMonitor">实时监控</span>
                    </button>
                    <button class="tab" data-tab="routes" onclick="setTab('routes')">
                        <i class="fas fa-route"></i>
                        <span data-i18n="apiRoutes">API路由</span>
                    </button>
                    <button class="tab" data-tab="status" onclick="setTab('status')">
                        <i class="fas fa-server"></i>
                        <span data-i18n="serverStatus">服务器状态</span>
                    </button>
                </div>
                
                <!-- Real-time Monitor Tab -->
                <div id="monitor" class="content active">
                    <div class="request-monitor">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                            <h2 style="color: var(--text-primary); font-size: 1.6rem; margin: 0;">
                                <i class="fas fa-comments"></i>
                                实时请求流 ({len(requests)} 最新)
                            </h2>
                            <button onclick="clearRequestLog()" 
                                    style="background: var(--error-gradient); color: white; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; transition: var(--transition); display: flex; align-items: center; gap: 8px;"
                                    onmouseover="this.style.transform='translateY(-2px) scale(1.05)'"
                                    onmouseout="this.style.transform='none'">
                                <i class="fas fa-trash"></i>
                                <span data-i18n="clearLog">清空日志</span>
                            </button>
                        </div>
                        <div class="bubble-container">
                            {''.join([f'''
                            <div class="request-bubble" onclick="showRequestDetail('{req['id']}')">
                                <div class="bubble-status status-{('timeout' if req.get('status') == 'timeout' else 'success' if req.get('response_status') and 200 <= req.get('response_status', 0) < 300 else 'warning' if req.get('response_status') and 400 <= req.get('response_status', 0) < 500 else 'error' if req.get('response_status') and req.get('response_status', 0) >= 500 else 'pending')}">
                                    {req.get('response_status', '⋯' if req.get('status') != 'timeout' else '⏱')}
                                </div>
                                <div class="bubble-method">{req['method']}</div>
                                <div class="bubble-path">{req['path'][:40] + '...' if len(req['path']) > 40 else req['path']}</div>
                                <div class="bubble-time">
                                    <span>{req['datetime'].split(' ')[1] if ' ' in req['datetime'] else req['datetime']}</span>
                                    <span>{f"{req['response_time']*1000:.0f}ms" if req.get('response_time') else ''}</span>
                                </div>
                            </div>
                            ''' for req in reversed(requests)]) if requests else '''
                            <div class="empty-state">
                                <i class="fas fa-inbox"></i>
                                <h3>还没有请求</h3>
                                <p>请求到达时将显示在这里</p>
                            </div>
                            '''}
                        </div>
                    </div>
                    
                    <!-- Request Details Modal -->
                    <div id="requestModal" class="request-modal" onclick="closeModal(event)">
                        <div class="modal-content" onclick="event.stopPropagation()">
                            <button class="modal-close" onclick="closeModal()">
                                <i class="fas fa-times"></i>
                            </button>
                            <div id="modalBody"></div>
                        </div>
                    </div>
                </div>
                
                <!-- API Routes Tab -->
                <div id="routes" class="content">
                    <div class="route-groups">
                        {''.join([f'''
                        <div class="route-group">
                            <h3>
                                <i class="fas fa-folder"></i>
                                {group.title()} Group
                                <span style="background: var(--bg-light); color: var(--text-muted); padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; margin-left: auto;">
                                    {len(routes)} routes
                                </span>
                            </h3>
                            {''.join([f'''
                            <div class="route-item">
                                <span class="method-badge method-{route['method']}">{route['method']}</span>
                                <span class="route-path">{route['path']}</span>
                                <span class="feature-badge {'feature-enabled' if route.get('cache') else 'feature-disabled'}">
                                    <i class="fas fa-{'memory' if route.get('cache') else 'ban'}"></i>
                                    Cache
                                </span>
                                <span class="feature-badge {'feature-enabled' if route.get('ratelimit') else 'feature-disabled'}">
                                    <i class="fas fa-{'tachometer-alt' if route.get('ratelimit') else 'ban'}"></i>
                                    Rate Limit
                                </span>
                                <span class="feature-badge {'feature-enabled' if route.get('auth') else 'feature-disabled'}">
                                    <i class="fas fa-{'lock' if route.get('auth') else 'unlock'}"></i>
                                    Auth
                                </span>
                            </div>
                            ''' for route in routes])}
                        </div>
                        ''' for group, routes in grouped_routes.items()]) if grouped_routes else '''
                        <div class="empty-state">
                            <i class="fas fa-route"></i>
                            <h3>No routes registered</h3>
                            <p>Register some API routes to see them here</p>
                        </div>
                        '''}
                    </div>
                </div>
                
                <!-- Server Status Tab -->
                <div id="status" class="content">
                    <div class="grid">
                        <div class="card">
                            <h2><i class="fas fa-server"></i> <span data-i18n="serverStats">服务器统计</span></h2>
                            <div class="stat">
                                <span class="label" data-i18n="runtime">运行时间:</span>
                                <span class="value" data-stat="uptime">{stats['uptime_formatted']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="totalRequests">总请求数:</span>
                                <span class="value" data-stat="total_requests">{stats['total_requests']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="activeRequests">活跃请求:</span>
                                <span class="value" data-stat="active_requests">{stats['active_requests']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="errorCount">错误数:</span>
                                <span class="value error" data-stat="total_errors">{stats['total_errors']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="avgResponseTime">平均响应时间:</span>
                                <span class="value" data-stat="avg_response_time">{stats['avg_response_time_formatted']}</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h2><i class="fas fa-memory"></i> <span data-i18n="cacheStatus">缓存状态</span></h2>
                            <div class="stat">
                                <span class="label" data-i18n="enabled">已启用:</span>
                                <span class="value">{cache_info.get('enabled', False)}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="size">大小:</span>
                                <span class="value">{cache_info.get('size', 0)}/{cache_info.get('max_size', 0)}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="hitRate">命中率:</span>
                                <span class="value success" data-stat="cache_hit_rate">{stats['cache_hit_rate']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="hits">命中:</span>
                                <span class="value success" data-stat="cache_hits">{stats['cache_hits']}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="misses">未命中:</span>
                                <span class="value warning" data-stat="cache_misses">{stats['cache_misses']}</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h2><i class="fas fa-desktop"></i> <span data-i18n="systemInfo">系统信息</span></h2>
                            <div class="stat">
                                <span class="label" data-i18n="cpuUsage">CPU使用率:</span>
                                <span class="value" data-stat="cpu_usage">{system_info.get('cpu', {}).get('usage', 'N/A')}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="memoryUsage">内存使用率:</span>
                                <span class="value" data-stat="memory_percent">{system_info.get('memory', {}).get('percent', 'N/A')}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="diskUsage">磁盘使用率:</span>
                                <span class="value" data-stat="disk_percent">{system_info.get('disk', {}).get('percent', 'N/A')}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="pythonVersion">Python版本:</span>
                                <span class="value">{system_info.get('python_version', 'N/A')}</span>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h2><i class="fas fa-shield-alt"></i> <span data-i18n="requestLimits">请求限制</span></h2>
                            <div class="stat">
                                <span class="label" data-i18n="enabled">已启用:</span>
                                <span class="value">{ratelimit_info.get('enabled', False)}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="timeWindow">时间窗口:</span>
                                <span class="value">{ratelimit_info.get('window', 60)}s</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="maxRequests">最大请求数:</span>
                                <span class="value">{ratelimit_info.get('max_requests', 100)}</span>
                            </div>
                            <div class="stat">
                                <span class="label" data-i18n="blocked">被阻止:</span>
                                <span class="value error" data-stat="ratelimit_hits">{stats['ratelimit_hits']}</span>
                            </div>
                        </div>
                    </div>
                    
                    {''.join([f'''
                    <div class="card" style="margin-top: 25px;">
                        <h2><i class="fas fa-exclamation-triangle"></i> 最近错误 ({len(errors)})</h2>
                        <div class="error-log">
                            {''.join([f'''
                            <div class="error-item">
                                <div class="error-header">
                                    <span class="error-type">{e['type']}</span>
                                    <span class="error-time">{e['datetime']}</span>
                                </div>
                                <div style="margin-bottom: 10px;">
                                    <span class="method-badge method-{e.get('method', 'GET')}">{e.get('method', 'GET')}</span>
                                    <span style="font-family: monospace; margin-left: 10px; font-weight: 600;">{e['path']}</span>
                                </div>
                                <div class="error-details">{e['error'][:300]}{'...' if len(e['error']) > 300 else ''}</div>
                            </div>
                            ''' for e in reversed(errors[:10])])}
                        </div>
                    </div>
                    ''']) if errors else '''
                    <div class="card" style="margin-top: 25px;">
                        <div class="empty-state">
                            <i class="fas fa-check-circle"></i>
                            <h3>没有错误记录</h3>
                            <p>您的服务器运行正常！</p>
                        </div>
                    </div>
                    '''}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        stats = self.get_stats()
        
        # 判断健康状态
        status = "healthy"
        issues = []
        
        if stats['active_requests'] > 100:
            status = "degraded"
            issues.append("High active requests")
        
        if stats['total_errors'] > stats['total_requests'] * 0.1:
            status = "unhealthy"
            issues.append("High error rate")
        
        if self.stats.average_response_time > 5:
            status = "degraded"
            issues.append("Slow response time")
        
        return {
            'status': status,
            'uptime': stats['uptime'],
            'issues': issues,
            'debug_mode': self.debug_mode,
            'stats': {
                'requests': stats['total_requests'],
                'errors': stats['total_errors'],
                'active': stats['active_requests']
            }
        }