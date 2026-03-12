# OAuth 2.0 Server 使用指南

## 概述

这是一个用 Go 编写的完整 OAuth 2.0 授权服务器，支持标准的 OAuth 2.0 和 OIDC (OpenID Connect) 协议。

**已与 proxy 项目配置完全兼容**，可以直接替换 Casdoor 使用。

## 功能特性

- ✅ **Authorization Code Flow** (授权码模式)
- ✅ **Client Credentials Flow** (客户端凭证模式)
- ✅ **Refresh Token** (刷新令牌)
- ✅ **JWT Token** (RS256 签名)
- ✅ **JWKS 端点** (用于 token 验证)
- ✅ **OIDC Discovery** (自动发现配置)
- ✅ **Token Introspection** (token 验证端点)
- ✅ **用户信息端点**
- ✅ **现代化登录页面** (企业级 UI 设计)

## 快速开始

### 1. 启动 OAuth 2.0 Server

```bash
cd oauth-server

# Windows
start-oauth-server.bat

# Linux/macOS
chmod +x start-oauth-server.sh
./start-oauth-server.sh

# 或者直接运行
go run cmd/main.go
```

启动后访问：http://localhost:8081

### 2. 默认配置

**默认配置已与 proxy 项目完全兼容**，无需修改即可使用。

| 配置项 | 值 |
|--------|-----|
| 服务器端口 | 8081 |
| Issuer | http://localhost:8081 |
| 默认客户端 ID | `proxy-client` |
| 默认客户端密钥 | `proxy-secret-2026` |
| 默认回调 URIs | `http://localhost:8080/oauth2callback`, `http://localhost:8501/oauth2callback` |

### 3. 测试用户

| 用户 ID | 用户名 | 邮箱 |
|--------|--------|------|
| user-001 | Admin User | admin@example.com |
| user-002 | Test User | test@example.com |

---

## 配置说明

### 环境变量配置

复制 `.env.example` 为 `.env`，可以根据需要修改配置：

```bash
# 服务器配置
SERVER_PORT=8081
ISSUER=http://localhost:8081

# CORS 配置
ENABLE_CORS=true
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:8501,http://localhost:3000

# 默认客户端配置（与 proxy 项目一致）
DEFAULT_CLIENT_ID=proxy-client
DEFAULT_CLIENT_SECRET=proxy-secret-2026
DEFAULT_REDIRECT_URIS=http://localhost:8080/oauth2callback,http://localhost:8501/oauth2callback

# 测试用户配置
DEFAULT_USERS=user-001:Admin User:admin@example.com:admin,user-002:Test User:test@example.com:test
```

### 自定义客户端

如需添加新的客户端，修改环境变量即可：

```bash
DEFAULT_CLIENT_ID=your-client-id
DEFAULT_CLIENT_SECRET=your-client-secret
DEFAULT_REDIRECT_URIS=http://your-domain.com/callback
```

---

## API 端点

### OAuth 2.0 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/oauth/authorize` | GET | 授权端点 |
| `/oauth/login` | POST | 登录处理 |
| `/oauth/quick-login` | POST | 快速登录（测试用） |
| `/oauth/token` | POST | Token 端点 |
| `/oauth/userinfo` | GET | 用户信息 |
| `/oauth/introspect` | POST | Token 验证 |

### OIDC 发现端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/.well-known/openid-configuration` | GET | OIDC 配置发现 |
| `/.well-known/jwks.json` | GET | JWKS 公钥 |

---

## 使用示例

### 1. Authorization Code Flow

#### 步骤 1: 重定向用户到授权页面

```
GET http://localhost:8081/oauth/authorize?
    client_id=proxy-client&
    redirect_uri=http://localhost:8080/oauth2callback&
    response_type=code&
    scope=openid%20email%20profile&
    state=random-state-string&
    nonce=random-nonce-string
```

#### 步骤 2: 用户登录并授权

用户会被重定向到登录页面，登录后会自动跳转回 redirect_uri，并带上 authorization code：

```
http://localhost:8080/oauth2callback?code=AUTH_CODE&state=random-state-string
```

#### 步骤 3: 用授权码交换 Token

```bash
POST http://localhost:8081/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=AUTH_CODE&
redirect_uri=http://localhost:8080/oauth2callback&
client_id=proxy-client&
client_secret=proxy-secret-2026
```

响应：

```json
{
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "scope": "openid email profile",
    "refresh_token": "dGhpc2lzYXJhbmRvbXJlZnJlc2h0b2tlbg"
}
```

#### 步骤 4: 使用 Access Token 获取用户信息

```bash
GET http://localhost:8081/oauth/userinfo
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

### 2. Client Credentials Flow (机器对机器)

```bash
POST http://localhost:8081/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=proxy-client&
client_secret=proxy-secret-2026&
scope=openid
```

响应：

```json
{
    "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "Bearer",
    "expires_in": 3600,
    "scope": "openid"
}
```

---

### 3. Refresh Token

```bash
POST http://localhost:8081/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=dGhpc2lzYXJhbmRvbXJlZnJlc2h0b2tlbg&
client_id=proxy-client&
client_secret=proxy-secret-2026
```

---

### 4. Token Introspection (验证 Token)

```bash
POST http://localhost:8081/oauth/introspect
Content-Type: application/x-www-form-urlencoded

token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

响应（有效 token）：

```json
{
    "active": true,
    "scope": "openid email profile",
    "client_id": "proxy-client",
    "token_type": "Bearer",
    "exp": 1735700000,
    "iat": 1735696400,
    "sub": "authenticated-user",
    "iss": "http://localhost:8081"
}
```

响应（无效 token）：

```json
{
    "active": false
}
```

---

## Proxy 项目接入指南

### 修改 proxy 配置

编辑 `proxy/.env` 文件：

```bash
# 修改为 OAuth 2.0 Server 的地址
CASDOOR_SERVER_URL=http://localhost:8081

# 使用 OAuth 2.0 Server 的客户端配置
CLIENT_ID=proxy-client
CLIENT_SECRET=proxy-secret-2026

# 回调 URL
REDIRECT_URI=http://localhost:8080/oauth2callback

# 后端
STREAMLIT_BACKEND=http://localhost:8501
PROXY_PORT=8080
```

### 修改 proxy 代码

由于 OAuth 2.0 Server 的端点路径与 Casdoor 略有不同，需要修改 `proxy/main.go`：

```go
// 修改 OAuth2 配置
oauth2Config = &oauth2.Config{
    ClientID:     clientID,
    ClientSecret: clientSecret,
    RedirectURL:  redirectURI,
    Scopes:       []string{"openid", "email", "profile"},
    Endpoint: oauth2.Endpoint{
        AuthURL:  casdoorServerURL + "/oauth/authorize",
        TokenURL: casdoorServerURL + "/oauth/token",
    },
}

// 修改用户信息获取
userInfoEndpoint := casdoorServerURL + "/oauth/userinfo"
```

---

## 添加新的 OAuth 客户端

### 方法 1: 修改代码

编辑 `internal/store/store.go` 中的 `initDefaultClients` 函数：

```go
func (s *MemoryStore) initDefaultClients() {
    // ... 现有代码 ...

    // 添加新客户端
    newClient := &models.OAuthClient{
        ClientID:     "your-client-id",
        ClientSecret: "your-client-secret",
        Name:         "Your Application Name",
        RedirectURIs: []string{
            "http://your-domain.com/callback",
        },
        Scopes:    []string{"openid", "email", "profile"},
        IsActive:  true,
        CreatedAt: time.Now(),
    }
    s.clients[newClient.ClientID] = newClient
}
```

### 方法 2: 添加管理 API（待实现）

可以添加一个管理 API 来动态添加客户端。

---

## 生产环境配置

### 1. 环境变量

创建 `.env` 文件：

```bash
# 服务器配置
SERVER_PORT=8081
ISSUER=https://oauth.your-domain.com

# CORS 配置
ENABLE_CORS=true
ALLOWED_ORIGINS=https://your-domain.com,https://app.your-domain.com

# 客户端配置
DEFAULT_CLIENT_ID=your-production-client-id
DEFAULT_CLIENT_SECRET=your-production-client-secret
```

### 2. 使用 HTTPS

生产环境必须使用 HTTPS。可以使用 Nginx 反向代理：

```nginx
server {
    listen 443 ssl;
    server_name oauth.your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 3. 持久化存储

当前使用内存存储，重启后数据会丢失。生产环境建议使用数据库：

- PostgreSQL
- MySQL
- Redis

---

## 安全建议

1. **生产环境必须使用 HTTPS**
2. **使用强随机数的 Client Secret**
3. **定期轮换密钥**
4. **限制 Token 有效期**
5. **启用 PKCE（针对公共客户端）**
6. **监控异常登录行为**

---

## 项目结构

```
oauth-server/
├── cmd/
│   └── main.go                 # 程序入口
├── internal/
│   ├── config/                 # 配置管理
│   ├── handler/
│   │   └── oauth.go            # HTTP 处理器
│   ├── middleware/             # Gin 中间件
│   ├── models/
│   │   └── models.go           # 数据模型
│   ├── service/
│   │   └── oauth.go            # OAuth 业务逻辑
│   ├── store/
│   │   └── store.go            # 数据存储
│   └── token/
│       └── token.go            # Token 管理
├── templates/
│   ├── login.html              # 登录页面
│   └── error.html              # 错误页面
├── .env.example                # 环境变量示例
├── go.mod                      # Go 模块配置
├── build.sh                    # 构建脚本
└── start-oauth-server.bat      # Windows 启动脚本
```

---

## 故障排查

### 问题 1: Token 验证失败

**可能原因:**
- Token 已过期
- Token 签名不匹配
- 时钟不同步

**解决方法:**
- 检查 Token 的 exp 字段
- 使用 JWKS 端点验证签名
- 同步服务器时间

### 问题 2: 回调 URL 不匹配

**错误:** `redirect_uri_mismatch`

**解决方法:**
- 确保请求中的 redirect_uri 与客户端配置中的一致
- 检查 URL 编码是否正确

### 问题 3: CORS 错误

**错误:** `No 'Access-Control-Allow-Origin' header`

**解决方法:**
- 启用 CORS: `ENABLE_CORS=true`
- 添加允许的源：`ALLOWED_ORIGINS=https://your-domain.com`

---

## 参考文档

- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)
- [OIDC Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [JWT RFC 7519](https://tools.ietf.org/html/rfc7519)
- [JWKS RFC 7517](https://tools.ietf.org/html/rfc7517)

---

## 许可证

MIT License
