# 空调节能率智能测算工具 - 代理架构

## 架构说明

本应用使用 **Go-Gin 反向代理** + **Streamlit 后端** 的架构：

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

## 快速开始

### 1. 配置环境变量

首次运行时，复制并编辑配置文件：

```bash
cd proxy
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 2. 启动 Streamlit 后端

```bash
# 方式 1: 使用启动脚本
start-streamlit.bat

# 方式 2: 直接启动
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

### 3. 启动 Go-Gin 代理

```bash
# 方式 1: 使用启动脚本（推荐）
cd proxy
start-proxy.bat

# 方式 2: 直接运行（开发模式）
cd proxy
go run main.go

# 方式 3: 运行编译后的程序
cd proxy
.\conditioner-proxy.exe
```

### 4. 访问应用

启动完成后，访问：**http://localhost:8080**

- 未登录会自动重定向到 Casdoor 登录页
- 登录成功后自动跳回应用
- 用户信息显示在 Cookie 中（代理层管理）

---

## 配置说明

### 环境变量文件 (proxy/.env)

```bash
# Casdoor 认证配置
CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
CLIENT_ID=your-client-id
CLIENT_SECRET=your-client-secret

# 代理配置
REDIRECT_URI=http://localhost:8080/oauth2callback
STREAMLIT_BACKEND=http://localhost:8501
PROXY_PORT=8080

# Cookie 配置
COOKIE_SECRET=change-this-secret-in-production
SESSION_COOKIE_NAME=session_token
USER_INFO_COOKIE_NAME=user_info
```

### 环境变量优先级

配置加载顺序（优先级从高到低）：
1. 系统环境变量
2. `proxy/.env` 文件
3. 代码中的默认值

### 生产环境配置

**1. 使用系统环境变量：**

```bash
export CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
export CLIENT_ID=your-production-client-id
export CLIENT_SECRET=your-production-client-secret
export REDIRECT_URI=https://your-domain.com/oauth2callback
export STREAMLIT_BACKEND=http://localhost:8501
export PROXY_PORT=8080
export COOKIE_SECRET=your-production-random-secret
```

**2. 更新 Casdoor 回调 URL：**

在 Casdoor 管理后台添加生产环境回调 URL：
```
https://your-domain.com/oauth2callback
```

**3. 生成安全的 Cookie Secret：**

```bash
# Linux/Mac
openssl rand -base64 32

# PowerShell
[System.Web.Security.Membership]::GeneratePassword(32, 4)

# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 认证流程

```
1. 用户访问 http://localhost:8080
         ↓
2. Go-Gin 检测未登录 → 重定向到 /login
         ↓
3. 生成 OAuth2 授权 URL → 跳转到 Casdoor
         ↓
4. 用户登录 Casdoor
         ↓
5. Casdoor 回调 /oauth2callback (带 authorization code)
         ↓
6. Go-Gin 用 code 交换 token 和用户信息
         ↓
7. 设置 session cookie + user_info cookie
         ↓
8. 重定向到应用首页
         ↓
9. Go-Gin 代理请求到 Streamlit (8501)
```

---

## 项目结构

```
conditioner_saving/
├── app.py                          # Streamlit 主应用
├── core/                           # 核心模块
│   ├── skill_caller.py
│   ├── data_filler.py
│   └── excel_calculator.py
├── proxy/                          # Go-Gin 代理服务
│   ├── main.go                     # 代理主程序
│   ├── go.mod                      # Go 模块配置
│   ├── go.sum                      # 依赖校验
│   ├── .env                        # 环境配置（不提交）
│   ├── .env.example                # 配置示例
│   ├── conditioner-proxy.exe       # 编译后的代理程序
│   └── start-proxy.bat             # 启动脚本
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml
├── start-streamlit.bat             # Streamlit 启动脚本
├── PROXY_ARCHITECTURE.md           # 架构文档
└── README.md                       # 项目说明
```

---

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
start-streamlit.bat

# 终端 2: 启动代理
cd proxy
start-proxy.bat
```

---

## 部署到生产环境

### 1. 编译 Go 代理

```bash
cd proxy
go build -o conditioner-proxy
```

### 2. 配置环境变量

```bash
# Linux/Mac
export CASDOOR_SERVER_URL=https://casdoor.mogulinker.com
export CLIENT_ID=your-production-client-id
export CLIENT_SECRET=your-production-client-secret
export REDIRECT_URI=https://your-domain.com/oauth2callback
export STREAMLIT_BACKEND=http://localhost:8501
export COOKIE_SECRET=$(openssl rand -base64 32)
```

```powershell
# Windows PowerShell
$env:CASDOOR_SERVER_URL="https://casdoor.mogulinker.com"
$env:CLIENT_ID="your-production-client-id"
$env:CLIENT_SECRET="your-production-client-secret"
$env:REDIRECT_URI="https://your-domain.com/oauth2callback"
$env:STREAMLIT_BACKEND="http://localhost:8501"
```

### 3. 启动服务

```bash
# 启动 Streamlit（后台运行）
nohup streamlit run app.py --server.port 8501 --server.address 0.0.0.0 &

# 启动代理（后台运行）
nohup ./conditioner-proxy &
```

### 4. 使用 Docker（推荐）

创建 `Dockerfile`：

```dockerfile
FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY proxy/ .
RUN go mod download && go build -o conditioner-proxy .

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/conditioner-proxy /usr/local/bin/
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

EXPOSE 8080 8501
CMD ["conditioner-proxy"]
```

构建并运行：

```bash
docker build -t conditioner-saving .
docker run -d -p 8080:8080 -p 8501:8501 \
  -e CASDOOR_SERVER_URL=https://casdoor.mogulinker.com \
  -e CLIENT_ID=xxx \
  -e CLIENT_SECRET=xxx \
  -e REDIRECT_URI=https://your-domain.com/oauth2callback \
  conditioner-saving
```

---

## 故障排查

### 问题 1: 登录后循环跳转

**检查项**:
- Casdoor 回调 URL 配置是否正确
- Cookie 是否被浏览器阻止
- 系统时间是否同步
- `.env` 文件中的 `REDIRECT_URI` 是否与 Casdoor 配置一致

### 问题 2: 代理无法连接 Streamlit

**检查项**:
- Streamlit 是否启动在 8501 端口
- 防火墙是否阻止 8501 端口
- `STREAMLIT_BACKEND` 环境变量是否正确

```bash
# 检查 Streamlit 是否运行
curl http://localhost:8501/health

# 检查代理是否运行
curl http://localhost:8080/health
```

### 问题 3: Go 依赖安装失败

```bash
cd proxy
go mod tidy
go get -u github.com/gin-gonic/gin
go get -u github.com/coreos/go-oidc/v3/oidc
go get -u golang.org/x/oauth2
go get -u github.com/joho/godotenv
```

### 问题 4: 环境变量未生效

**检查方法**:

```bash
# 查看当前环境变量
echo $CASDOOR_SERVER_URL  # Linux/Mac
echo %CASDOOR_SERVER_URL% # Windows CMD
$env:CASDOOR_SERVER_URL   # Windows PowerShell

# 检查 .env 文件是否存在
ls -la proxy/.env
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 认证代理 | Go 1.25+ | Gin 框架 + OIDC |
| OAuth 库 | go-oidc/v3 | CoreOS OIDC 库 |
| 环境配置 | godotenv | .env 文件加载 |
| Web 框架 | Gin | 高性能 HTTP 框架 |
| 后端应用 | Python 3.8+ | Streamlit |
| 认证服务 | Casdoor | OIDC 身份提供商 |

---

## 安全注意事项

1. **生产环境必须使用 HTTPS** - 配置反向代理（Nginx/Caddy）处理 SSL
2. **修改 COOKIE_SECRET 为随机强密钥** - 使用工具生成 32 位以上随机字符串
3. **定期更新 CLIENT_SECRET** - 在 Casdoor 后台轮换密钥
4. **启用 CSRF 保护** - Gin 中间件已内置
5. **限制会话有效期** - 修改 Cookie MaxAge
6. **.env 文件不要提交到 Git** - 已添加到 .gitignore

---

## 参考文档

- [Gin 框架文档](https://gin-gonic.com/)
- [go-oidc 文档](https://github.com/coreos/go-oidc)
- [Casdoor 文档](https://casdoor.org/)
- [Streamlit 文档](https://docs.streamlit.io/)
