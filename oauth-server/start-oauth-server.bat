@echo off
echo ===========================================
echo   Starting OAuth 2.0 Authorization Server
echo ===========================================

cd /d "%~dp0"

REM 检查 Go 是否安装
where go >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Go is not installed or not in PATH
    echo Please install Go from https://golang.org/dl/
    pause
    exit /b 1
)

echo [INFO] Go version:
go version

REM 安装依赖
echo [INFO] Installing dependencies...
go mod tidy

REM 运行服务器
echo [INFO] Starting OAuth 2.0 Server...
go run cmd/main.go

pause
