@echo off
echo ==========================================
echo   Starting Go-Gin Proxy Server
echo ==========================================
echo   Port: 8080
echo   Casdoor: https://casdoor.mogulinker.com
echo   Backend: http://localhost:8501
echo ==========================================
echo.
cd /d "%~dp0"
go run main.go
