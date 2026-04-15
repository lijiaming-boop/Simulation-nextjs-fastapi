#!/bin/bash

echo "==========================================="
echo "  Building OAuth 2.0 Authorization Server"
echo "==========================================="

cd "$(dirname "$0")"

# 检查 Go 是否安装
if ! command -v go &> /dev/null; then
    echo "[ERROR] Go is not installed or not in PATH"
    echo "Please install Go from https://golang.org/dl/"
    exit 1
fi

echo "[INFO] Go version:"
go version

# 安装依赖
echo "[INFO] Installing dependencies..."
go mod tidy

# 编译
echo "[INFO] Building..."
GOOS=linux GOARCH=amd64 go build -o oauth-server cmd/main.go
GOOS=windows GOARCH=amd64 go build -o oauth-server.exe cmd/main.go
GOOS=darwin GOARCH=amd64 go build -o oauth-server-darwin cmd/main.go

echo "[INFO] Build completed!"
echo "  - oauth-server.exe (Windows)"
echo "  - oauth-server (Linux)"
echo "  - oauth-server-darwin (macOS)"
