# Manager_API - 轻量API服务器框架

基于FastAPI的极简API框架，一个回调处理所有请求。

## 快速开始

```python
from Manager_API import FastAPIServer

# 创建服务器
server = FastAPIServer()

# 配置参数
server.host = '0.0.0.0'        # 服务器监听地址
server.port = 8000             # 服务器端口
server.debug = True            # 调试模式（生产环境设为False）

# 注册路由
server.append("GET", "/api/hello", name="问候")
server.append("POST", "/api/users", name="创建用户")

# 处理回调
def api_handler(data):
    if data['path'] == '/api/hello':
        return {"message": "Hello World!"}
    elif data['path'] == '/api/users':
        user = data['body']
        return {"status": 201, "data": user}
    
    return {"status": 404, "error": "Not Found"}

server.set_callback(api_handler)
server.start()
```

## 配置参数

所有配置通过属性设置，无需配置文件：

```python
# 基础配置
SYS_API_SERVER.host = '0.0.0.0'          # 服务器监听地址
SYS_API_SERVER.port = 8000               # 服务器端口
SYS_API_SERVER.title = "My API Server"   # API标题
SYS_API_SERVER.description = "API描述"   # API描述
SYS_API_SERVER.version = "1.0.0"         # API版本
SYS_API_SERVER.debug = False             # 调试模式（开启debug面板）

# CORS跨域
SYS_API_SERVER.enable_cors = True        # 启用CORS
SYS_API_SERVER.cors = [                  # 允许的源
    "http://localhost:3000",
    "https://mydomain.com",
    "http://192.168.1.*"                  # 支持通配符
]

# 性能配置
SYS_API_SERVER.max_concurrent = 1000     # 最大并发数
SYS_API_SERVER.request_timeout = 60      # 请求超时时间(秒)

# 缓存配置
SYS_API_SERVER.enable_cache = True       # 启用缓存
SYS_API_SERVER.cache_ttl = 300          # 缓存时间(秒)
SYS_API_SERVER.cache_max_size = 1000    # 最大缓存条目

# 限流配置
SYS_API_SERVER.enable_ratelimit = True   # 启用限流
SYS_API_SERVER.ratelimit_window = 60     # 限流窗口(秒)
SYS_API_SERVER.ratelimit_max = 100       # 窗口内最大请求数

# 监控配置
SYS_API_SERVER.enable_monitor = True     # 启用监控
SYS_API_SERVER.enable_metrics = True     # 启用指标收集
SYS_API_SERVER.enable_health = True      # 启用健康检查
```

## 完整示例

```python
from Manager_API import FastAPIServer

# 初始化服务器
server = FastAPIServer()

# 配置服务器
server.host = '0.0.0.0'
server.port = 8080
server.debug = True
server.title = "用户管理API"
server.description = "简单的用户管理系统"
server.enable_cors = True
server.cors = ["http://localhost:3000", "https://frontend.com"]

# 注册API路由
server.append("GET", "/api/users", group="用户", name="获取用户列表")
server.append("GET", "/api/users/{id}", group="用户", name="获取用户详情")
server.append("POST", "/api/users", group="用户", name="创建用户")
server.append("PUT", "/api/users/{id}", group="用户", name="更新用户")
server.append("DELETE", "/api/users/{id}", group="用户", name="删除用户")
server.append("GET", "/api/health", group="系统", name="健康检查")

# 模拟数据库
users_db = {
    "1": {"id": "1", "name": "张三", "email": "zhang@example.com"},
    "2": {"id": "2", "name": "李四", "email": "li@example.com"}
}

# API处理函数
def handle_api(data):
    method = data['type']
    path = data['path']
    
    # 健康检查
    if path == '/api/health':
        return {"status": "healthy", "timestamp": data['timestamp']}
    
    # 获取用户列表
    elif path == '/api/users' and method == 'GET':
        return {"users": list(users_db.values()), "total": len(users_db)}
    
    # 获取单个用户
    elif path.startswith('/api/users/') and method == 'GET':
        user_id = data['params']['id']
        if user_id in users_db:
            return {"user": users_db[user_id]}
        return {"status": 404, "error": "用户不存在"}
    
    # 创建用户
    elif path == '/api/users' and method == 'POST':
        user_data = data['body']
        user_id = str(len(users_db) + 1)
        user_data['id'] = user_id
        users_db[user_id] = user_data
        return {"status": 201, "user": user_data, "message": "用户创建成功"}
    
    # 更新用户
    elif path.startswith('/api/users/') and method == 'PUT':
        user_id = data['params']['id']
        if user_id in users_db:
            users_db[user_id].update(data['body'])
            return {"user": users_db[user_id], "message": "用户更新成功"}
        return {"status": 404, "error": "用户不存在"}
    
    # 删除用户
    elif path.startswith('/api/users/') and method == 'DELETE':
        user_id = data['params']['id']
        if user_id in users_db:
            del users_db[user_id]
            return {"status": 204, "message": "用户删除成功"}
        return {"status": 404, "error": "用户不存在"}
    
    # 404处理
    return {"status": 404, "error": "API接口不存在"}

# 设置回调并启动
server.set_callback(handle_api)

if __name__ == "__main__":
    print("🚀 启动API服务器...")
    if server.start():
        print(f"✅ 服务器运行在 http://localhost:{server.port}")
        print(f"📊 Debug面板: http://localhost:{server.port}/_debug")
        print(f"📖 API文档: http://localhost:{server.port}/docs")
    else:
        print("❌ 服务器启动失败")
```

## 回调函数数据结构

```python
data = {
    "type": "POST",                    # HTTP方法
    "path": "/api/users/123",         # 请求路径
    "method": "POST",                 # 同type，兼容性
    "params": {"id": "123"},          # 路径参数
    "query": {"page": 1, "size": 10}, # 查询参数
    "body": {"name": "用户名"},        # 请求体
    "headers": {...},                 # 请求头
    "cookies": {...},                 # Cookies
    "client": "192.168.1.100",       # 客户端IP
    "request_id": "req_xxx",          # 请求ID
    "timestamp": 1234567890.123,      # 时间戳
    "files": [...],                   # 上传文件
    "route_info": {...}               # 路由信息
}
```

## 响应格式

```python
# JSON响应
return {"message": "成功"}

# 带状态码的响应
return {
    "status": 201,
    "data": {"id": 1, "name": "用户"},
    "headers": {"X-Custom": "value"}
}

# 文本响应
return "Plain text response"

# 空响应
return None  # 返回204 No Content
```

## 内置端点

- `/_debug` - 调试面板（需开启debug模式）
- `/_health` - 健康检查
- `/_routes` - 路由列表
- `/_metrics` - 性能指标

## 高级功能

### 动态路由
```python
server.append("GET", "/api/users/{id}/posts/{post_id}", name="用户文章")

def handle(data):
    user_id = data['params']['id']        # 获取路径参数
    post_id = data['params']['post_id']   # 获取路径参数
    return {"user_id": user_id, "post_id": post_id}
```

### 路由级缓存和限流
```python
# 启用缓存
server.append("GET", "/api/data", cache=True)

# 自定义限流
server.append("POST", "/api/upload", 
              ratelimit={"max": 5, "window": 60})  # 每分钟5次
```

### 文件上传
```python
def handle(data):
    if data['path'] == '/api/upload':
        files = data.get('files', [])
        for file in files:
            # file包含: field_name, filename, content_type, file
            with open(f"uploads/{file['filename']}", "wb") as f:
                f.write(file['file'].read())
        return {"message": f"上传了{len(files)}个文件"}
```

## 生产环境配置

```python
# 生产环境建议配置
server.debug = False              # 关闭调试模式
server.host = '0.0.0.0'          # 监听所有接口
server.port = 80                 # 标准HTTP端口
server.max_concurrent = 2000     # 根据服务器调整
server.enable_cache = True       # 启用缓存提升性能
server.enable_ratelimit = True   # 防止滥用
server.cors = ["https://yourdomain.com"]  # 限制跨域源
```

## 依赖安装

```bash
pip install fastapi uvicorn
```

可选依赖（用于系统监控）：
```bash
pip install psutil
```

---

这就是全部！极简配置，强大功能。