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
server.start()  # 默认非阻塞启动
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
    # 阻塞启动（程序会一直运行直到手动停止）
    if server.start(block=True):
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

### 路由级缓存、限流和授权
```python
# 启用缓存
server.append("GET", "/api/data", cache=True)

# 自定义限流
server.append("POST", "/api/upload", 
              ratelimit={"max": 5, "window": 60})  # 每分钟5次

# 启用授权验证
server.append("POST", "/api/admin/users", auth=True)
server.append("DELETE", "/api/admin/delete", auth=True)
```

### 授权验证
在注册路由时启用授权，然后在回调函数中处理授权逻辑：

```python
# 注册需要授权的路由
server.append("GET", "/api/profile", auth=True, name="获取用户资料")
server.append("POST", "/api/admin/settings", auth=True, name="管理员设置")

def api_handler(data):
    # 检查是否需要授权
    if data.get('route_info', {}).get('auth'):
        # 获取授权头
        auth_header = data.get('headers', {}).get('authorization')
        
        if not auth_header:
            return {"status": 401, "error": "未提供授权信息"}
        
        # 验证token（示例）
        token = auth_header.replace('Bearer ', '')
        if not verify_token(token):
            return {"status": 403, "error": "授权验证失败"}
        
        # 授权成功，可以从token中提取用户信息
        user_id = extract_user_from_token(token)
        data['user_id'] = user_id  # 添加用户信息到请求数据
    
    # 处理业务逻辑
    if data['path'] == '/api/profile':
        return get_user_profile(data.get('user_id'))
    elif data['path'] == '/api/admin/settings':
        if not is_admin(data.get('user_id')):
            return {"status": 403, "error": "需要管理员权限"}
        return update_admin_settings(data['body'])
    
    return {"status": 404, "error": "接口不存在"}

def verify_token(token):
    # 实现token验证逻辑
    # 例如：JWT验证、数据库查询等
    return token == "valid_token_example"

def extract_user_from_token(token):
    # 从token提取用户ID
    return "user_123"

def is_admin(user_id):
    # 检查用户是否为管理员
    return user_id in ["admin_user_1", "admin_user_2"]
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

## 服务器启动方式

Manager_API 支持两种启动方式：

### 非阻塞启动（默认）
```python
# 非阻塞启动，服务器在后台运行，主线程继续执行
server.start()  # 等同于 server.start(block=False)

# 适用场景：
# - 集成到其他应用中
# - 需要在同一程序中运行多个服务
# - 测试环境或开发调试
```

### 阻塞启动
```python
# 阻塞启动，程序会一直运行直到手动停止
server.start(block=True)

# 适用场景：
# - 生产环境部署
# - 独立运行的API服务
# - 需要程序持续运行的情况
```

### 完整启动示例
```python
import time
from Manager_API import FastAPIServer

server = FastAPIServer()
server.host = '0.0.0.0'
server.port = 8000
server.debug = True

# 注册路由
server.append("GET", "/api/test")

def api_handler(data):
    return {"message": "Hello World"}

server.set_callback(api_handler)

# 选择启动方式
if __name__ == "__main__":
    print("选择启动方式:")
    print("1. 阻塞启动 (推荐)")
    print("2. 非阻塞启动")
    
    choice = input("请输入选择 (1/2): ")
    
    if choice == "1":
        # 阻塞启动
        print("🚀 阻塞启动服务器...")
        if server.start(block=True):
            print(f"✅ 服务器运行在 http://localhost:{server.port}")
            print(f"📊 Debug面板: http://localhost:{server.port}/_debug")
        else:
            print("❌ 服务器启动失败")
    else:
        # 非阻塞启动（默认）
        print("🚀 非阻塞启动服务器...")
        if server.start():  # 默认就是非阻塞，可以省略 block=False
            print(f"✅ 服务器已在后台启动: http://localhost:{server.port}")
            print("📝 主线程继续运行，可以执行其他任务")
            
            # 主线程可以继续执行其他代码
            for i in range(60):
                print(f"⏰ 服务器运行中... {i+1}s")
                time.sleep(1)
            
            print("🛑 程序结束，服务器将自动停止")
        else:
            print("❌ 服务器启动失败")
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

# 生产环境推荐使用阻塞启动
server.start(block=True)  # 明确指定阻塞启动
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