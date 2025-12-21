# 空调节能率智能测算工具 - 部署指南

本文档提供详细的部署、配置和运维指南。

## 📋 目录

- [环境要求](#环境要求)
- [依赖安装](#依赖安装)
- [配置文件设置](#配置文件设置)
- [启动应用](#启动应用)
- [生产部署](#生产部署)
- [常见问题](#常见问题)
- [运维建议](#运维建议)

---

## 环境要求

### 系统要求

**操作系统**：
- Linux（推荐 Ubuntu 20.04+ / CentOS 7+）
- macOS 10.15+
- Windows 10+ (仅用于开发测试)

**硬件要求**：
- CPU: 2 核心及以上
- 内存: 4GB 及以上（推荐 8GB）
- 硬盘: 10GB 可用空间

**网络要求**：
- 内网访问（8501 端口）
- 支持 5-10 人并发访问

### Python 环境

- **Python 版本**：3.8 或更高（推荐 3.9+）
- **包管理器**：pip 或 conda

验证 Python 版本：
```bash
python3 --version
# 应输出：Python 3.8.x 或更高
```

### 可选依赖

**Excel 引擎**（用于 xlwings，提升计算精度）：

- **Linux**：
  ```bash
  # Ubuntu/Debian
  sudo apt-get update
  sudo apt-get install libreoffice

  # CentOS/RHEL
  sudo yum install libreoffice
  ```

- **macOS**：
  ```bash
  # 安装 Microsoft Excel（推荐）
  # 或安装 LibreOffice
  brew install --cask libreoffice
  ```

- **Windows**：
  - 安装 Microsoft Excel（推荐）
  - 或安装 LibreOffice: https://www.libreoffice.org/download/

**注意**：如果未安装 Excel/LibreOffice，系统会自动降级使用 openpyxl（公式读取模式），精度略低。

---

## 依赖安装

### 1. 克隆项目

```bash
# 进入工作目录
cd /path/to/your/workspace

# 克隆项目（替换为实际的仓库地址）
git clone <repository-url>
cd conditioner_saving
```

### 2. 创建虚拟环境（推荐）

```bash
# 使用 venv
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# Windows: venv\Scripts\activate

# 或使用 conda
conda create -n conditioner_saving python=3.9
conda activate conditioner_saving
```

### 3. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

依赖列表（`requirements.txt`）：
```txt
streamlit>=1.28.0
pandas>=2.0.0
openpyxl>=3.1.0
xlwings>=0.30.0
pytest>=7.0.0
plotly>=5.0.0
```

### 4. 验证安装

```bash
# 检查 Streamlit 版本
streamlit --version

# 检查依赖是否正确安装
python3 -c "import streamlit, pandas, openpyxl, xlwings, plotly; print('All dependencies installed successfully')"
```

---

## 配置文件设置

### 1. Streamlit 服务器配置

创建 `.streamlit/config.toml`：

```toml
[server]
# 端口号（默认 8501）
port = 8501

# 监听地址
# "0.0.0.0" - 允许所有 IP 访问（生产环境）
# "localhost" - 仅本机访问（开发环境）
address = "0.0.0.0"

# 无头模式（服务器环境必须启用）
headless = true

# CORS 设置
enableCORS = false
enableXsrfProtection = true

# 文件上传限制（MB）
maxUploadSize = 10

[browser]
# 自动打开浏览器（生产环境建议关闭）
gatherUsageStats = false

[theme]
# 主题配置（可选）
primaryColor = "#1f77b4"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f0f2f6"
textColor = "#262730"
font = "sans serif"
```

### 2. 密码保护配置

创建 `.streamlit/secrets.toml`：

```toml
# 管理员密码（用于下载完整 Excel 计算表）
admin_password = "your_secure_password"
```

**安全建议**：
- 使用强密码（至少 12 位，包含大小写字母、数字、特殊字符）
- 定期更换密码
- 不要将 `secrets.toml` 提交到版本控制（已在 `.gitignore` 中排除）

### 3. 防火墙配置（仅 Linux 生产环境）

**Ubuntu/Debian（使用 ufw）**：
```bash
# 开放 8501 端口
sudo ufw allow 8501/tcp

# 查看防火墙状态
sudo ufw status
```

**CentOS/RHEL（使用 firewalld）**：
```bash
# 开放 8501 端口
sudo firewall-cmd --zone=public --add-port=8501/tcp --permanent
sudo firewall-cmd --reload

# 查看开放端口
sudo firewall-cmd --list-ports
```

---

## 启动应用

### 开发环境

**前台运行**（调试模式）：
```bash
streamlit run app.py
```

访问地址：`http://localhost:8501`

**查看日志**：日志直接输出到终端

### 生产环境

#### 方法 1: 后台运行（nohup）

```bash
# 创建日志目录
mkdir -p logs

# 后台启动
nohup streamlit run app.py > logs/streamlit.log 2>&1 &

# 查看进程
ps aux | grep streamlit

# 查看日志
tail -f logs/streamlit.log

# 停止服务
pkill -f "streamlit run app.py"
```

#### 方法 2: systemd 服务（推荐）

见下一章节"生产部署"。

---

## 生产部署

### 使用 systemd 服务（推荐）

**优点**：
- 开机自启
- 进程守护（崩溃自动重启）
- 日志管理
- 服务状态监控

#### 1. 创建服务配置文件

创建 `/etc/systemd/system/conditioner-saving.service`：

```ini
[Unit]
Description=Air Conditioner Energy Saving Calculator
After=network.target

[Service]
Type=simple
User=your_username
Group=your_groupname
WorkingDirectory=/path/to/conditioner_saving
Environment="PATH=/path/to/conditioner_saving/venv/bin"
ExecStart=/path/to/conditioner_saving/venv/bin/streamlit run app.py
Restart=always
RestartSec=10

# 标准输出和错误日志
StandardOutput=append:/var/log/conditioner-saving/stdout.log
StandardError=append:/var/log/conditioner-saving/stderr.log

# 安全加固（可选）
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

**配置说明**：
- `User`: 替换为实际运行用户（不要用 root）
- `Group`: 替换为实际用户组
- `WorkingDirectory`: 替换为项目实际路径
- `Environment`: 替换为虚拟环境的实际路径
- `ExecStart`: 替换为虚拟环境中 streamlit 的实际路径

#### 2. 创建日志目录

```bash
sudo mkdir -p /var/log/conditioner-saving
sudo chown your_username:your_groupname /var/log/conditioner-saving
```

#### 3. 启用和启动服务

```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable conditioner-saving

# 启动服务
sudo systemctl start conditioner-saving

# 查看服务状态
sudo systemctl status conditioner-saving
```

#### 4. 服务管理命令

```bash
# 启动服务
sudo systemctl start conditioner-saving

# 停止服务
sudo systemctl stop conditioner-saving

# 重启服务
sudo systemctl restart conditioner-saving

# 查看服务状态
sudo systemctl status conditioner-saving

# 查看服务日志
sudo journalctl -u conditioner-saving -f

# 查看最近 100 行日志
sudo journalctl -u conditioner-saving -n 100

# 禁用服务（取消开机自启）
sudo systemctl disable conditioner-saving
```

### 使用 Docker（可选）

创建 `Dockerfile`（需自行配置）：

```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露端口
EXPOSE 8501

# 启动命令
CMD ["streamlit", "run", "app.py"]
```

构建和运行：
```bash
# 构建镜像
docker build -t conditioner-saving:latest .

# 运行容器
docker run -d \
  --name conditioner-saving \
  -p 8501:8501 \
  -v $(pwd)/.streamlit:/app/.streamlit:ro \
  conditioner-saving:latest

# 查看日志
docker logs -f conditioner-saving

# 停止容器
docker stop conditioner-saving

# 删除容器
docker rm conditioner-saving
```

---

## 常见问题

### 1. 无法访问应用

**问题**：浏览器无法打开 `http://<服务器IP>:8501`

**排查步骤**：
```bash
# 1. 检查服务是否运行
ps aux | grep streamlit
# 或
sudo systemctl status conditioner-saving

# 2. 检查端口是否监听
sudo netstat -tlnp | grep 8501
# 或
sudo ss -tlnp | grep 8501

# 3. 检查防火墙
sudo ufw status  # Ubuntu
sudo firewall-cmd --list-ports  # CentOS

# 4. 检查 config.toml 中的 address
cat .streamlit/config.toml | grep address
# 应为 address = "0.0.0.0"

# 5. 查看应用日志
tail -f logs/streamlit.log
# 或
sudo journalctl -u conditioner-saving -f
```

### 2. 上传文件后报错

**问题**：上传 Excel 文件后提示"数据提取失败"

**可能原因**：
1. 调研表格式不符合标准
2. 关键字段缺失
3. 文件损坏

**解决方法**：
```bash
# 1. 检查是否为标准模板
# 参考：00_sample/02-中央空调节能调研表.xlsx

# 2. 查看详细错误日志
tail -f logs/streamlit.log

# 3. 使用测试数据验证系统
cp 00_sample/02-中央空调节能调研表.xlsx tmp/test_survey.xlsx
# 在 UI 中上传 test_survey.xlsx
```

### 3. 计算结果为"模拟数据"

**问题**：结果页面显示"⚠️ 注意: 此结果为模拟数据 (xlwings环境未配置)"

**原因**：未安装 Microsoft Excel 或 LibreOffice

**解决方法**：
```bash
# Linux (Ubuntu/Debian)
sudo apt-get install libreoffice

# Linux (CentOS/RHEL)
sudo yum install libreoffice

# macOS
brew install --cask libreoffice

# Windows
# 安装 Microsoft Excel 或 LibreOffice
```

**注意**：模拟数据仅用于演示，精度较低，生产环境必须配置 Excel 引擎。

### 4. Skills 调用超时

**问题**：长时间卡在"正在提取调研表数据，请稍候..."

**可能原因**：
1. Claude API 超时
2. 网络连接问题
3. 文件过大

**解决方法**：
```bash
# 1. 检查网络连接
ping api.anthropic.com

# 2. 增加超时时间
# 编辑 app.py，修改 SkillCaller(timeout=300) 中的 timeout 值

# 3. 检查文件大小
ls -lh tmp/upload_survey.xlsx
# 应 < 10MB
```

### 5. 依赖安装失败

**问题**：`pip install -r requirements.txt` 报错

**解决方法**：
```bash
# 1. 升级 pip
pip install --upgrade pip

# 2. 单独安装失败的包
pip install streamlit
pip install pandas
pip install openpyxl
pip install xlwings
pip install plotly
pip install pytest

# 3. 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 运维建议

### 日志管理

**日志文件位置**：
- systemd 服务：`/var/log/conditioner-saving/`
- nohup 方式：`logs/streamlit.log`
- 临时文件：`tmp/`

**日志清理策略**：
```bash
# 创建日志清理脚本 cleanup_logs.sh
cat > cleanup_logs.sh <<'EOF'
#!/bin/bash
# 清理 7 天前的日志
find /var/log/conditioner-saving -name "*.log" -mtime +7 -delete
# 清理临时文件
find tmp/ -type f -mtime +1 -delete
echo "$(date): Logs cleaned" >> /var/log/conditioner-saving/cleanup.log
EOF

chmod +x cleanup_logs.sh

# 添加到 crontab（每天凌晨 2 点执行）
crontab -e
# 添加以下行：
0 2 * * * /path/to/conditioner_saving/cleanup_logs.sh
```

### 数据备份

**备份配置文件**：
```bash
# 创建备份脚本 backup_config.sh
cat > backup_config.sh <<'EOF'
#!/bin/bash
BACKUP_DIR="/backup/conditioner_saving/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 备份配置文件
cp -r .streamlit $BACKUP_DIR/
cp -r config $BACKUP_DIR/
cp requirements.txt $BACKUP_DIR/

echo "$(date): Config backed up to $BACKUP_DIR" >> logs/backup.log
EOF

chmod +x backup_config.sh

# 添加到 crontab（每周日凌晨 3 点执行）
0 3 * * 0 /path/to/conditioner_saving/backup_config.sh
```

### 性能监控

**监控指标**：
- CPU 使用率
- 内存使用率
- 磁盘 I/O
- 响应时间

**使用 systemd 资源限制**（可选）：

编辑 `/etc/systemd/system/conditioner-saving.service`，添加：
```ini
[Service]
# 内存限制（最大 2GB）
MemoryMax=2G

# CPU 限制（最大 50%）
CPUQuota=50%
```

重新加载：
```bash
sudo systemctl daemon-reload
sudo systemctl restart conditioner-saving
```

### 安全加固

1. **限制访问 IP**（使用 Nginx 反向代理）：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # 限制访问 IP
    allow 192.168.1.0/24;  # 内网 IP 段
    deny all;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

2. **定期更新密码**：
```bash
# 编辑 .streamlit/secrets.toml
nano .streamlit/secrets.toml

# 重启服务使密码生效
sudo systemctl restart conditioner-saving
```

3. **定期更新依赖**：
```bash
# 检查可更新的包
pip list --outdated

# 更新所有包（谨慎操作，建议先在测试环境验证）
pip install --upgrade -r requirements.txt

# 重启服务
sudo systemctl restart conditioner-saving
```

### 健康检查

创建健康检查脚本 `health_check.sh`：

```bash
#!/bin/bash

# 检查服务是否运行
if systemctl is-active --quiet conditioner-saving; then
    echo "✅ Service is running"
else
    echo "❌ Service is down, restarting..."
    sudo systemctl restart conditioner-saving
    exit 1
fi

# 检查端口是否监听
if ss -tlnp | grep -q ":8501"; then
    echo "✅ Port 8501 is listening"
else
    echo "❌ Port 8501 is not listening"
    exit 1
fi

# 检查 HTTP 响应
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501)
if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ HTTP response is OK"
else
    echo "❌ HTTP response is $HTTP_CODE"
    exit 1
fi

echo "$(date): Health check passed" >> logs/health_check.log
```

添加到 crontab（每 5 分钟检查一次）：
```bash
*/5 * * * * /path/to/conditioner_saving/health_check.sh
```

---

## 故障排查清单

| 问题 | 排查命令 | 解决方法 |
|------|----------|----------|
| 服务未运行 | `sudo systemctl status conditioner-saving` | `sudo systemctl start conditioner-saving` |
| 端口未监听 | `sudo ss -tlnp \| grep 8501` | 检查 config.toml，重启服务 |
| 防火墙阻止 | `sudo ufw status` | `sudo ufw allow 8501/tcp` |
| 内存不足 | `free -h` | 增加内存或设置 swap |
| 磁盘满 | `df -h` | 清理日志和临时文件 |
| Python 环境错误 | `python3 --version` | 使用 Python 3.8+ |
| 依赖缺失 | `pip list` | `pip install -r requirements.txt` |
| Excel 引擎未配置 | 查看结果页面警告 | 安装 LibreOffice 或 Excel |

---

## 联系支持

如遇到无法解决的问题，请联系：
- 项目负责人：[联系方式]
- 技术支持：[联系方式]

提供以下信息以便快速定位问题：
1. 错误截图
2. 日志文件（`logs/streamlit.log` 或 `sudo journalctl -u conditioner-saving -n 100`）
3. 系统环境（OS 版本、Python 版本）
4. 问题复现步骤

---

**最后更新**：2025-12-21
**文档版本**：1.0
