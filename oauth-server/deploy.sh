#!/bin/bash

echo "==========================================="
echo "  Deploying OAuth Server to Remote Server"
echo "==========================================="

# 配置
REMOTE_USER="mogu"
REMOTE_HOST="mogu-test-algo-ai-product"
REMOTE_PATH="/home/mogu/lingzhi_app/conditioner_saving/oauth-server"
SERVICE_NAME="conditioner-oauth-server"

# 进入脚本所在目录
cd "$(dirname "$0")"

# 1. 构建 Linux 版本
echo "[1/4] Building for Linux..."
GOOS=linux GOARCH=amd64 go build -o oauth-server cmd/main.go
if [ $? -ne 0 ]; then
    echo "[ERROR] Build failed"
    exit 1
fi

# 2. 上传到服务器
echo "[2/4] Uploading to server..."
scp oauth-server ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/
if [ $? -ne 0 ]; then
    echo "[ERROR] Upload failed"
    exit 1
fi

# 3. 重启服务
echo "[3/4] Restarting service..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl restart ${SERVICE_NAME}"
if [ $? -ne 0 ]; then
    echo "[ERROR] Service restart failed"
    exit 1
fi

# 4. 检查服务状态
echo "[4/4] Checking service status..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl status ${SERVICE_NAME} --no-pager"

echo ""
echo "==========================================="
echo "  Deployment completed!"
echo "==========================================="
echo ""
echo "To view logs, run:"
echo "  ssh ${REMOTE_USER}@${REMOTE_HOST} 'sudo journalctl -u ${SERVICE_NAME} -f'"

