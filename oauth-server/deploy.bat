@echo off
echo ===========================================
echo   Deploying OAuth Server to Remote Server
echo ===========================================

REM 配置
set REMOTE_USER=mogu
set REMOTE_HOST=mogu-test-algo-ai-product
set REMOTE_PATH=/home/mogu/lingzhi_app/conditioner_saving/oauth-server
set SERVICE_NAME=conditioner-oauth-server

REM 进入脚本所在目录
cd /d "%~dp0"

REM 1. 构建 Linux 版本
echo [1/4] Building for Linux...
set GOOS=linux
set GOARCH=amd64
go build -o oauth-server cmd/main.go
if errorlevel 1 (
    echo [ERROR] Build failed
    exit /b 1
)

REM 2. 上传到服务器
echo [2/4] Uploading to server...
scp oauth-server %REMOTE_USER%@%REMOTE_HOST%:%REMOTE_PATH%/
if errorlevel 1 (
    echo [ERROR] Upload failed
    exit /b 1
)

REM 3. 重启服务
echo [3/4] Restarting service...
ssh %REMOTE_USER%@%REMOTE_HOST% "sudo systemctl restart %SERVICE_NAME%"
if errorlevel 1 (
    echo [ERROR] Service restart failed
    exit /b 1
)

REM 4. 检查服务状态
echo [4/4] Checking service status...
ssh %REMOTE_USER%@%REMOTE_HOST% "sudo systemctl status %SERVICE_NAME% --no-pager"

echo.
echo ===========================================
echo   Deployment completed!
echo ===========================================
echo.
echo To view logs, run:
echo   ssh %REMOTE_USER%@%REMOTE_HOST% "sudo journalctl -u %SERVICE_NAME% -f"

pause

