# OAuth 2.0 Server 快速开始

## 1. 启动服务器

### Windows
双击运行：
```
start-oauth-server.bat
```

或命令行运行：
```bash
go run cmd/main.go
```

### Linux/macOS
```bash
chmod +x build.sh
./build.sh

# 运行
./oauth-server-macos  # macOS
./oauth-server-linux  # Linux
```

## 2. 验证服务器

服务器启动后，访问：
- 首页：http://localhost:8081
- 健康检查：http://localhost:8081/health
- OIDC 发现：http://localhost:8081/.well-known/openid-configuration
- JWKS: http://localhost:8081/.well-known/jwks.json

## 3. 默认配置（与 proxy 一致）

| 配置项 | 值 |
|--------|-----|
| 端口 | 8081 |
| 客户端 ID | `proxy-client` |
| 客户端密钥 | `proxy-secret-2026` |
| 回调 URIs | `http://localhost:8080/oauth2callback`, `http://localhost:8501/oauth2callback` |

## 4. 测试用户

| 用户 ID | 姓名 | 邮箱 |
|--------|------|------|
| user-001 | Admin User | admin@example.com |
| user-002 | Test User | test@example.com |

## 5. OAuth 2.0 授权流程示例

### 步骤 1: 访问授权页面

在浏览器中打开：
```
http://localhost:8081/oauth/authorize?
    client_id=proxy-client&
    redirect_uri=http://localhost:8080/oauth2callback&
    response_type=code&
    scope=openid%20email%20profile&
    state=test123
```

### 步骤 2: 登录

- 点击测试用户快速登录
- 或使用用户名/密码登录（任意输入即可）

### 步骤 3: 获取授权码

登录后会重定向到：
```
http://localhost:8080/oauth2callback?code=AUTH_CODE&state=test123
```

### 步骤 4: 用授权码换取 Token

```bash
curl -X POST http://localhost:8081/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=AUTH_CODE" \
  -d "redirect_uri=http://localhost:8080/oauth2callback" \
  -d "client_id=proxy-client" \
  -d "client_secret=proxy-secret-2026"
```

### 步骤 5: 使用 Token 访问用户信息

```bash
curl http://localhost:8081/oauth/userinfo \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

## 6. 接入 Proxy 项目

编辑 `proxy/.env`:
```bash
CASDOOR_SERVER_URL=http://localhost:8081
CLIENT_ID=proxy-client
CLIENT_SECRET=proxy-secret-2026
```

然后重启 proxy 即可。

详细文档请查看：
- [README.md](README.md) - 完整文档
- [PROXY_INTEGRATION.md](PROXY_INTEGRATION.md) - Proxy 接入指南
