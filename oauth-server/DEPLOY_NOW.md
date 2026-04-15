# 立即部署 - 修复 State 参数编码问题

## 问题分析

从日志发现，state 参数没有被 URL 编码，导致：

**原始 state:**
```
/auth/oauth2/login.php?wantsurl=https%3A%2F%2Fmogulinker.moodlecloud.com%2F&sesskey=1zDlWgEs53&id=3
```

**错误的重定向 URL:**
```
https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=/auth/oauth2/login.php?wantsurl=https%3A%2F%2Fmogulinker.moodlecloud.com%2F&sesskey=1zDlWgEs53&id=3
```

问题：`&sesskey` 和 `&id` 被当作独立的 URL 参数，而不是 state 的一部分！

## 已修复

在 `oauth-server/internal/handler/oauth.go` 中：
- 添加了 `net/url` 导入
- 使用 `url.QueryEscape()` 对 code 和 state 参数进行编码

修复后的重定向 URL 应该是：
```
https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=%2Fauth%2Foauth2%2Flogin.php%3Fwantsurl%3Dhttps%253A%252F%252Fmogulinker.moodlecloud.com%252F%26sesskey%3D1zDlWgEs53%26id%3D3
```

## 部署步骤

### 1. 构建（已完成 ✅）

```powershell
cd D:\source\ai\conditioner_saving\oauth-server
powershell -ExecutionPolicy Bypass -File build-linux.ps1
```

### 2. 上传到服务器

**方法 A: 使用 SCP（如果配置了 SSH）**

```bash
# 替换为实际的服务器地址
scp oauth-server mogu@<服务器IP>:/home/mogu/lingzhi_app/conditioner_saving/oauth-server/
```

**方法 B: 使用 WinSCP 或其他 SFTP 工具**

1. 连接到服务器
2. 上传 `oauth-server` 文件到 `/home/mogu/lingzhi_app/conditioner_saving/oauth-server/`
3. 确保文件有执行权限

**方法 C: 手动复制（如果有直接访问权限）**

直接将 `oauth-server` 文件复制到服务器对应目录

### 3. 在服务器上重启服务

SSH 登录到服务器后执行：

```bash
# 进入目录
cd /home/mogu/lingzhi_app/conditioner_saving/oauth-server

# 确保文件有执行权限
chmod +x oauth-server

# 重启服务
sudo systemctl restart conditioner-oauth-server

# 查看服务状态
sudo systemctl status conditioner-oauth-server

# 查看实时日志
sudo journalctl -u conditioner-oauth-server -f
```

### 4. 测试

1. 访问 Moodle OAuth 登录链接
2. 完成登录
3. 查看日志，应该看到正确编码的 redirect_url：

```
Authorization complete: code=xxx, state=/auth/oauth2/login.php?wantsurl=..., redirect_url=https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=%2Fauth%2Foauth2%2Flogin.php%3F...
```

注意 state 参数现在应该是 URL 编码的（`%2F` 代表 `/`，`%3F` 代表 `?`，`%26` 代表 `&`）

### 5. 验证成功

如果修复成功，应该看到：
1. ✅ 授权完成日志（带编码的 state）
2. ✅ Token 交换请求日志
3. ✅ Token 交换成功日志
4. ✅ Moodle 成功登录，不再显示会话超时错误

## 快速命令（复制粘贴）

**在本地 Windows 上（已完成构建）：**
```powershell
# 如果需要重新构建
cd D:\source\ai\conditioner_saving\oauth-server
powershell -ExecutionPolicy Bypass -File build-linux.ps1
```

**在服务器上：**
```bash
# 重启服务并查看日志
sudo systemctl restart conditioner-oauth-server && sudo journalctl -u conditioner-oauth-server -f
```

## 预期的日志输出

**修复前（错误）：**
```
redirect_url=https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=/auth/oauth2/login.php?wantsurl=https%3A%2F%2Fmogulinker.moodlecloud.com%2F&sesskey=1zDlWgEs53&id=3
```

**修复后（正确）：**
```
redirect_url=https://mogulinker.moodlecloud.com/admin/oauth2callback.php?code=xxx&state=%2Fauth%2Foauth2%2Flogin.php%3Fwantsurl%3Dhttps%253A%252F%252Fmogulinker.moodlecloud.com%252F%26sesskey%3D1zDlWgEs53%26id%3D3
```

## 如果还有问题

如果部署后仍然有问题，请提供：
1. 完整的日志输出（从授权到 token 交换）
2. Moodle 显示的错误信息
3. 浏览器开发者工具中的网络请求详情

