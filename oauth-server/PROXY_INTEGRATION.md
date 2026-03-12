# Proxy 项目接入 OAuth 2.0 Server 指南

## 概述

本文档说明如何将现有的 proxy 项目从 Casdoor 迁移到自建的 OAuth 2.0 Server。

## 架构对比

### 原架构（Casdoor）

```
┌─────────────────┐
│   Casdoor       │
│  (外部服务)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Go-Gin Proxy  │
│   (端口 8080)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Streamlit     │
│   (端口 8501)    │
└─────────────────┘
```

### 新架构（OAuth 2.0 Server）

```
┌─────────────────┐
│ OAuth 2.0 Server│
│  (端口 8081)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Go-Gin Proxy  │
│   (端口 8080)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Streamlit     │
│   (端口 8501)    │
└─────────────────┘
```

---

## 接入步骤

### 步骤 1: 启动 OAuth 2.0 Server

```bash
cd oauth-server
start-oauth-server.bat
```

确认服务器启动成功：
```bash
curl http://localhost:8081/health
# 响应：{"issuer":"http://localhost:8081","status":"ok"}
```

### 步骤 2: 修改 proxy/.env

编辑 `proxy/.env` 文件：

```bash
# 原配置（Casdoor）
# CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
# CLIENT_ID=4edb1fca2280ea63894a
# CLIENT_SECRET=b78916090366cb34392b501c21853a23030cbbca

# 新配置（OAuth 2.0 Server）
CASDOOR_SERVER_URL=http://localhost:8081
CLIENT_ID=proxy-client
CLIENT_SECRET=proxy-secret-2026

# 其他配置保持不变
REDIRECT_URI=http://localhost:8080/oauth2callback
STREAMLIT_BACKEND=http://localhost:8501
PROXY_PORT=8080
COOKIE_SECRET=change-this-secret-in-production
```

### 步骤 3: 修改 proxy/main.go

需要修改 OIDC Provider 的初始化和端点配置：

```go
// 修改前（Casdoor）
provider, err = oidc.NewProvider(ctx, casdoorServerURL)

// 修改后（OAuth 2.0 Server - 手动配置端点）
// 由于 OAuth 2.0 Server 支持 OIDC Discovery，可以保持原配置不变
// 但需要确保端点路径正确
```

如果遇到问题，可以手动配置 OAuth2 端点：

```go
// 手动配置 OAuth2 端点
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
```

### 步骤 4: 修改用户信息获取逻辑

OAuth 2.0 Server 的用户信息端点返回的格式可能不同，需要调整：

```go
// 修改前（Casdoor 格式）
type UserInfo struct {
    Sub       string `json:"sub"`
    Name      string `json:"name"`
    Email     string `json:"email"`
    Avatar    string `json:"avatar"`
    LoginName string `json:"loginName"`  // 注意：CamelCase
}

// 修改后（OAuth 2.0 Server 格式）
type UserInfo struct {
    Sub       string `json:"sub"`
    Name      string `json:"name"`
    Email     string `json:"email"`
    Avatar    string `json:"avatar,omitempty"`
    LoginName string `json:"login_name,omitempty"`  // 注意：snake_case
}
```

### 步骤 5: 测试登录流程

1. 启动 OAuth 2.0 Server:
   ```bash
   cd oauth-server
   start-oauth-server.bat
   ```

2. 启动 Proxy:
   ```bash
   cd proxy
   start-proxy.bat
   ```

3. 访问 http://localhost:8080

4. 点击登录，应该跳转到 OAuth 2.0 Server 的登录页面

5. 使用测试用户登录：
   - 用户 ID: user-001
   - 或者点击快速登录按钮

---

## 端点映射

| 功能 | Casdoor | OAuth 2.0 Server |
|------|---------|------------------|
| 授权端点 | /oauth2/authorize | /oauth/authorize |
| Token 端点 | /api/oauth2/token | /oauth/token |
| 用户信息 | /api/userinfo | /oauth/userinfo |
| OIDC 发现 | /.well-known/openid-configuration | /.well-known/openid-configuration |
| JWKS | /.well-known/jwks | /.well-known/jwks.json |

---

## 完整代码示例

### proxy/main.go 修改示例

```go
package main

import (
    "context"
    "encoding/json"
    "fmt"
    "net/http"
    "net/http/httputil"
    "net/url"
    "os"
    "strings"
    "time"

    "github.com/coreos/go-oidc/v3/oidc"
    "github.com/gin-gonic/gin"
    "github.com/joho/godotenv"
    "golang.org/x/oauth2"
)

// ... 其他代码保持不变 ...

func init() {
    // 加载 .env 文件
    godotenv.Load()

    // 读取配置
    casdoorServerURL = getEnv("CASDOOR_SERVER_URL", "http://localhost:8081")
    clientID = getEnv("CLIENT_ID", "proxy-client")
    clientSecret = getEnv("CLIENT_SECRET", "proxy-secret-2026")
    redirectURI = getEnv("REDIRECT_URI", "http://localhost:8080/oauth2callback")
    streamlitBackend = getEnv("STREAMLIT_BACKEND", "http://localhost:8501")
    cookieSecret = []byte(getEnv("COOKIE_SECRET", "change-this-secret-in-production"))
    sessionCookieName = getEnv("SESSION_COOKIE_NAME", "session_token")
    userInfoCookieName = getEnv("USER_INFO_COOKIE_NAME", "user_info")
    proxyPort = getEnv("PROXY_PORT", "8080")

    // 初始化 OIDC Provider
    ctx := context.Background()
    var err error
    
    // 尝试使用 OIDC Discovery
    provider, err = oidc.NewProvider(ctx, casdoorServerURL)
    if err != nil {
        // 如果失败，手动配置
        fmt.Printf("OIDC Discovery failed: %v, using manual configuration\n", err)
        
        // 创建手动配置
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
        return
    }

    // 配置 OAuth2
    oauth2Config = &oauth2.Config{
        ClientID:     clientID,
        ClientSecret: clientSecret,
        RedirectURL:  redirectURI,
        Scopes:       []string{oidc.ScopeOpenID, "email", "profile"},
        Endpoint:     provider.Endpoint(),
    }

    // 配置 ID Token 验证器
    verifier = provider.Verifier(&oidc.Config{
        ClientID: clientID,
    })
}

// ... 其他代码保持不变 ...

// handleCallback 处理 OAuth 回调
func handleCallback(c *gin.Context) {
    state := c.Query("state")
    code := c.Query("code")

    // 验证 state
    savedState, err := c.Cookie("oauth_state")
    if err != nil || state != savedState {
        c.JSON(http.StatusBadRequest, gin.H{"error": "invalid state"})
        return
    }

    // 获取 nonce
    savedNonce, _ := c.Cookie("oauth_nonce")

    ctx := context.Background()

    // 交换 token
    token, err := oauth2Config.Exchange(ctx, code)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to exchange token: %v", err)})
        return
    }

    // 获取用户信息
    var userInfo UserInfo
    
    // 尝试从 ID Token 获取
    rawIDToken, ok := token.Extra("id_token").(string)
    if ok {
        idToken, err := verifier.Verify(ctx, rawIDToken)
        if err == nil {
            // 验证 nonce
            if idToken.Nonce == savedNonce {
                idToken.Claims(&userInfo)
            }
        }
    }

    // 如果 ID Token 中没有用户信息，从 userinfo endpoint 获取
    if userInfo.Sub == "" {
        userInfoEndpoint := casdoorServerURL + "/oauth/userinfo"
        resp, err := oauth2Config.Client(ctx, token).Get(userInfoEndpoint)
        if err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to get userinfo: %v", err)})
            return
        }
        defer resp.Body.Close()
        if err := json.NewDecoder(resp.Body).Decode(&userInfo); err != nil {
            c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("Failed to decode userinfo: %v", err)})
            return
        }
    }

    // 生成会话 token
    sessionToken := token.AccessToken

    // 设置 cookie
    c.SetCookie(sessionCookieName, sessionToken, 0, "/", "", false, true)

    // 设置用户信息 cookie
    userInfoJSON, _ := json.Marshal(userInfo)
    c.SetCookie(userInfoCookieName, string(userInfoJSON), 0, "/", "", false, false)

    // 重定向到应用首页
    c.Redirect(http.StatusTemporaryRedirect, "/")
}
```

---

## 常见问题

### Q1: OIDC Discovery 失败

**问题:** `oidc.NewProvider` 返回错误

**解决:** 
- 检查 OAuth 2.0 Server 是否启动
- 检查 URL 是否正确
- 使用手动配置 OAuth2 端点

### Q2: Token 验证失败

**问题:** `Failed to verify id_token`

**解决:**
- 检查 Client ID 是否匹配
- 检查时钟是否同步
- 查看 OAuth 2.0 Server 日志

### Q3: 用户信息为空

**问题:** 登录后用户信息为空

**解决:**
- 检查 `/oauth/userinfo` 端点是否可访问
- 检查 Access Token 是否有效
- 查看响应格式是否匹配

---

## 回滚方案

如果需要回滚到 Casdoor：

1. 恢复 `proxy/.env`:
   ```bash
   CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
   CLIENT_ID=your-original-client-id
   CLIENT_SECRET=your-original-client-secret
   ```

2. 重启 Proxy:
   ```bash
   cd proxy
   start-proxy.bat
   ```

---

## 下一步

1. **添加更多客户端**: 在 `internal/store/store.go` 中添加新的 OAuth 客户端

2. **持久化存储**: 将内存存储替换为数据库存储

3. **添加管理界面**: 创建 Web 管理界面管理客户端和用户

4. **启用 HTTPS**: 生产环境配置 SSL/TLS

5. **监控和日志**: 集成日志和监控系统

---

## 支持

如有问题，请查看：
- OAuth 2.0 Server 日志
- Proxy 日志
- 浏览器开发者工具中的网络请求

---

## 参考文档

- [OAuth 2.0 Server README](../oauth-server/README.md)
- [PROXY_ARCHITECTURE.md](../PROXY_ARCHITECTURE.md)
- [CASDOOR_SETUP.md](../CASDOOR_SETUP.md)
