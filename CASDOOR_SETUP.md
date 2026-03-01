# Casdoor 登录集成配置指南

## 概述

本应用已集成 Casdoor 统一身份认证系统，使用 OIDC (OpenID Connect) 协议进行用户登录验证。

## Casdoor 应用配置

### 1. 登录 Casdoor 管理后台

访问：https://casdoor.mogulinker.com/

### 2. 配置应用回调 URL

在 Casdoor 应用配置中，确保设置了正确的回调 URL：

#### 开发环境：
```
http://localhost:8501/oauth2callback
```

#### 生产环境（示例）：
```
http://192.168.31.236:8501/oauth2callback
http://120.239.79.100:8501/oauth2callback
```

**重要提示：** 回调 URL 必须与 `.streamlit/secrets.toml` 中的 `redirect_uri` 完全一致！

### 3. 当前配置信息

- **Casdoor 地址：** https://casdoor.mogulinker.com/
- **应用 ID (Client ID)：** 4edb1fca2280ea63894a
- **应用密钥 (Client Secret)：** b78916090366cb34392b501c21853a23030cbbca
- **OIDC 发现端点：** https://casdoor.mogulinker.com/.well-known/openid-configuration

## 本地配置文件

认证配置已保存在 `.streamlit/secrets.toml` 中：

```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "randomly-generated-strong-secret-key-change-in-production-2026"

[auth.casdoor]
client_id = "4edb1fca2280ea63894a"
client_secret = "b78916090366cb34392b501c21853a23030cbbca"
server_metadata_url = "https://casdoor.mogulinker.com/.well-known/openid-configuration"
```

**安全提示：**
1. `.streamlit/secrets.toml` 已在 `.gitignore` 中，不会提交到版本控制
2. 生产环境部署时，请修改 `cookie_secret` 为更安全的随机字符串
3. 生产环境需更新 `redirect_uri` 为实际的域名

## 使用流程

### 用户登录流程

1. 访问应用 URL (http://localhost:8501)
2. 点击页面顶部的 **"Log in"** 按钮
3. 跳转到 Casdoor 登录页面
4. 输入用户名和密码登录
5. 登录成功后自动跳转回应用

### 登录后功能

- 应用会在侧边栏显示当前登录用户信息
- 用户可以点击 **"登出"** 按钮退出登录
- 所有页面都需要登录后才能访问

## 部署到生产环境

### 1. 更新回调 URL

在 `.streamlit/secrets.toml` 中修改：

```toml
[auth]
redirect_uri = "https://your-domain.com/oauth2callback"  # 改为实际域名
cookie_secret = "your-strong-random-secret-here"        # 生成新的密钥
```

### 2. 在 Casdoor 中添加生产环境回调 URL

在 Casdoor 应用设置的 "Redirect URIs" 中添加：
```
https://your-domain.com/oauth2callback
```

### 3. 生成安全的 Cookie Secret

使用 Python 生成随机密钥：

```python
import secrets
print(secrets.token_urlsafe(32))
```

## 故障排查

### 问题1：点击登录后无反应

**可能原因：**
- authlib 库未安装

**解决方法：**
```bash
pip install authlib>=1.3.2
```

### 问题2：回调后显示错误

**可能原因：**
- Casdoor 应用配置中的回调 URL 与 secrets.toml 不一致

**解决方法：**
1. 检查 `.streamlit/secrets.toml` 中的 `redirect_uri`
2. 确保 Casdoor 应用配置中包含相同的 URL

### 问题3：认证配置错误

**可能原因：**
- secrets.toml 配置格式错误
- Casdoor 服务不可达

**解决方法：**
1. 检查 secrets.toml 格式是否正确
2. 访问 https://casdoor.mogulinker.com/.well-known/openid-configuration 确认服务可用
3. 查看应用启动日志中的错误信息

## 技术实现

本应用使用 Streamlit 的原生 OIDC 认证支持：

```python
# 在 app.py 中
user_info = st.login(provider="casdoor")

if not user_info:
    st.warning("请登录以访问应用")
    st.stop()

# 应用主逻辑...
```

这种方式的优点：
- 无需手动处理 OAuth 流程
- 自动管理会话和 token
- 内置安全防护（CSRF、XSS）
- 代码简洁易维护

## 参考文档

- [Streamlit 用户认证文档](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [Casdoor 官方文档](https://casdoor.org/docs/)
- [OIDC 协议规范](https://openid.net/connect/)
