# Moodle OAuth 集成调试指南

## 问题描述

Moodle 接入 OAuth 服务器后报错：**"您的会话很可能已超时。请检查您是否已登录或返回上一个屏幕并重新加载页面。"**

## 已完成的修复

### 1. 添加 Moodle 重定向 URI

已在配置中添加 Moodle 的回调地址：
```
https://mogulinker.moodlecloud.com/admin/oauth2callback.php
```

修改的文件：
- `oauth-server/conditioner-oauth-server.service` (第 12 行)
- `oauth-server/.env.example` (第 14 行)

### 2. 添加调试日志

在以下位置添加了详细的调试日志：

1. **授权完成时** (`completeAuthorization`):
   - 输出授权码、state 参数和重定向 URL

2. **Token 交换时** (`handleAuthorizationCodeGrant`):
   - 输出请求参数（code, clientID, redirectURI）
   - 输出交换结果或错误信息

### 3. 修改错误页面

将"返回首页"按钮改为"返回"，使用浏览器历史记录返回功能。

## 部署步骤

### 方法 1: 使用部署脚本（推荐）

**Windows:**
```bash
cd oauth-server
deploy.bat
```

**Linux/Mac:**
```bash
cd oauth-server
chmod +x deploy.sh
./deploy.sh
```

### 方法 2: 手动部署

1. **构建 Linux 版本:**
```bash
cd oauth-server
GOOS=linux GOARCH=amd64 go build -o oauth-server cmd/main.go
```

2. **上传到服务器:**
```bash
scp oauth-server mogu@mogu-test-algo-ai-product:/home/mogu/lingzhi_app/conditioner_saving/oauth-server/
```

3. **重启服务:**
```bash
ssh mogu@mogu-test-algo-ai-product "sudo systemctl restart conditioner-oauth-server"
```

4. **查看日志:**
```bash
ssh mogu@mogu-test-algo-ai-product "sudo journalctl -u conditioner-oauth-server -f"
```

## 调试流程

### 1. 重新测试 Moodle 登录

访问 Moodle OAuth 登录链接，完成登录流程。

### 2. 查看日志输出

在服务器上查看实时日志：
```bash
sudo journalctl -u conditioner-oauth-server -f
```

关注以下日志信息：

**登录成功后：**
```
Saved user info: Sub=xxx, Name=xxx, Mobile=xxx
Authorization complete: code=xxx, state=xxx, redirect_url=https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=xxx
```

**Token 交换请求：**
```
Token request: code=xxx, clientID=4edb1fca2280ea63894a, redirectURI=https://mogulinker.moodlecloud.com/admin/oauth2callback.php
Token exchange success: access_token=xxx..., id_token=xxx...
```

或者错误信息：
```
Token exchange error: ...
```

### 3. 检查可能的问题

#### 问题 A: 没有收到 Token 交换请求

**症状：** 只看到授权完成日志，没有 Token 请求日志

**可能原因：**
- Moodle 没有正确接收到授权码
- State 参数验证失败
- 重定向 URL 格式问题

**解决方案：**
1. 检查重定向 URL 是否正确
2. 确认 state 参数是否被正确传递
3. 检查 Moodle 的 OAuth 配置

#### 问题 B: Token 交换失败

**症状：** 看到 "Token exchange error" 日志

**可能原因：**
- 授权码已过期（10分钟有效期）
- 授权码已被使用
- redirect_uri 不匹配
- Client credentials 不正确

**解决方案：**
1. 检查错误信息
2. 确认 Moodle 配置的 client_id 和 client_secret 正确
3. 确认 redirect_uri 完全一致

#### 问题 C: Token 交换成功但 Moodle 仍报错

**症状：** 看到 "Token exchange success" 但 Moodle 显示会话超时

**可能原因：**
- ID Token 格式问题
- UserInfo 端点返回数据不符合 Moodle 要求
- Moodle 的会话管理问题

**解决方案：**
1. 检查 ID Token 的 claims
2. 测试 UserInfo 端点
3. 检查 Moodle 日志

## 测试 UserInfo 端点

获取 access_token 后，可以手动测试 UserInfo 端点：

```bash
curl -H "Authorization: Bearer <access_token>" \
  https://h-oauth.mogulinker.com/oauth/userinfo
```

应该返回：
```json
{
  "sub": "用户ID",
  "name": "用户名",
  "email": "手机号",
  "mobile": "手机号",
  "role": "角色ID",
  "role_name": "角色名称",
  ...
}
```

## Moodle OAuth 配置检查清单

在 Moodle 管理后台检查以下配置：

- [ ] Client ID: `4edb1fca2280ea63894a`
- [ ] Client Secret: `b78916090366cb34392b501c21853a23030cbbca`
- [ ] Authorization endpoint: `https://h-oauth.mogulinker.com/oauth/authorize`
- [ ] Token endpoint: `https://h-oauth.mogulinker.com/oauth/token`
- [ ] UserInfo endpoint: `https://h-oauth.mogulinker.com/oauth/userinfo`
- [ ] Scopes: `openid profile email`

## 下一步

1. 部署更新后的代码
2. 重新测试 Moodle 登录
3. 收集完整的日志信息
4. 根据日志分析具体问题

