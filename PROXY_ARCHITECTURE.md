# 空调节能率智能测算工具 - 代理架构

## 架构说明

本应用现在使用 **Go-Gin 反向代理** + **Streamlit 后端** 的架构：

```
                    ┌─────────────────┐
                    │   Casdoor       │
                    │  (认证服务)      │
                    └────────┬────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│              Go-Gin 代理服务 (端口 8080)                 │
│  - 处理 OAuth2/OIDC 认证                                 │
│  - 会话管理 (Cookie)                                     │
│  - 反向代理到 Streamlit                                  │
│  - 用户信息注入 (X-User-Info Header)                     │
└─────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────┐
│            Streamlit 应用 (端口 8501)                     │
│  - 空调节能率测算                                        │
│  - 数据提取和质量检查                                    │
│  - Excel 计算引擎                                        │
│  - 结果可视化                                            │
└─────────────────────────────────────────────────────────┘
```

## 启动方式

### 1. 启动 Streamlit 后端

```bash
# 方式 1: 直接启动
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

# 方式 2: 使用启动脚本
./start-streamlit.bat  # Windows
./start-streamlit.sh   # Linux/Mac
```

### 2. 启动 Go-Gin 代理

```bash
# 进入代理目录
cd proxy

# 安装依赖（首次运行）
go mod tidy

# 启动代理服务
go run main.go

# 或使用启动脚本
./start-proxy.bat  # Windows
./start-proxy.sh   # Linux/Mac
```

### 3. 访问应用

启动完成后，访问：**http://localhost:8080**

- 未登录会自动重定向到 Casdoor 登录页
- 登录成功后自动跳回应用
- 用户信息显示在 Cookie 中（代理层管理）

## 配置说明

### Go-Gin 代理配置

在 `proxy/main.go` 中配置：

```go
var (
    casdoorServerURL   = "https://casdoor.mogulinker.com"
    clientID           = "4edb1fca2280ea63894a"
    clientSecret       = "b78916090366cb34392b501c21853a23030cbbca"
    redirectURI        = "http://localhost:8080/oauth2callback"
    streamlitBackend   = "http://localhost:8501"
)
```

或通过环境变量配置：

```bash
export CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
export CLIENT_ID=4edb1fca2280ea63894a
export CLIENT_SECRET=b78916090366cb34392b501c21853a23030cbbca
export REDIRECT_URI=http://localhost:8080/oauth2callback
export STREAMLIT_BACKEND=http://localhost:8501
```

### Streamlit 配置

Streamlit 配置在 `.streamlit/config.toml` 中：

```toml
[server]
port = 8501
address = "0.0.0.0"
```

## 认证流程

1. 用户访问 `http://localhost:8080`
2. Go-Gin 检测到未登录，重定向到 `/login`
3. `/login` 生成 OAuth2 授权 URL，跳转到 Casdoor
4. 用户在 Casdoor 登录
5. Casdoor 回调到 `/oauth2callback`，携带 authorization code
6. Go-Gin 用 code 交换 token 和用户信息
7. Go-Gin 设置 session cookie 和用户信息 cookie
8. Go-Gin 重定向到应用首页
9. 后续请求携带 cookie，Go-Gin 验证后代理到 Streamlit

## 会话管理

- **session_token**: 存储 access token，用于标识会话
- **user_info**: 存储用户信息（JSON 格式），包含 name, email 等

Cookie 属性：
- HttpOnly: 防止 XSS 攻击
- Secure: 生产环境应启用（HTTPS）
- Path: /
- MaxAge: 24 小时

## 开发模式

### 仅开发 Streamlit 功能（跳过认证）

直接访问 Streamlit 后端：

```bash
streamlit run app.py --server.port 8501
# 访问 http://localhost:8501
```

### 完整测试（包含认证）

```bash
# 终端 1: 启动 Streamlit
streamlit run app.py --server.port 8501

# 终端 2: 启动代理
cd proxy && go run main.go

# 访问 http://localhost:8080
```

## 部署到生产环境

### 1. 编译 Go 代理

```bash
cd proxy
go build -o conditioner-proxy
```

### 2. 配置环境变量

```bash
export CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
export CLIENT_ID=your-client-id
export CLIENT_SECRET=your-client-secret
export REDIRECT_URI=https://your-domain.com/oauth2callback
export STREAMLIT_BACKEND=http://localhost:8501
```

### 3. 更新 Casdoor 回调 URL

在 Casdoor 管理后台添加生产环境回调 URL：
```
https://your-domain.com/oauth2callback
```

### 4. 启动服务

```bash
# 启动 Streamlit（后台运行）
nohup streamlit run app.py --server.port 8501 &

# 启动代理（后台运行）
nohup ./conditioner-proxy &
```

### 5. 使用 Docker（推荐）

```bash
# 构建镜像
docker build -t conditioner-saving .

# 启动容器
docker run -d -p 8080:8080 -p 8501:8501 \
  -e CASDOOR_SERVER_URL=https://casdoor.mogulinker.com \
  -e CLIENT_ID=xxx \
  -e CLIENT_SECRET=xxx \
  conditioner-saving
```

## 故障排查

### 问题 1: 登录后循环跳转

**检查项**:
- Casdoor 回调 URL 配置是否正确
- Cookie 是否被浏览器阻止
- 系统时间是否同步

### 问题 2: 代理无法连接 Streamlit

**检查项**:
- Streamlit 是否启动在 8501 端口
- 防火墙是否阻止 8501 端口

### 问题 3: Go 依赖安装失败

```bash
cd proxy
go mod tidy
go get -u github.com/gin-gonic/gin
go get -u github.com/coreos/go-oidc/v3/oidc
go get -u golang.org/x/oauth2
```

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 认证代理 | Go 1.21+ | Gin 框架 + OIDC |
| OAuth 库 | go-oidc/v3 | CoreOS OIDC 库 |
| Web 框架 | Gin | 高性能 HTTP 框架 |
| 后端应用 | Python 3.8+ | Streamlit |
| 认证服务 | Casdoor | OIDC 身份提供商 |

## 安全注意事项

1. **生产环境必须使用 HTTPS**
2. **修改 cookie_secret 为随机强密钥**
3. **定期更新 client_secret**
4. **启用 CSRF 保护**
5. **限制会话有效期**
