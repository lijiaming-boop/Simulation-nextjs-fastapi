@echo off
echo ==========================================
echo   Starting Go-Gin Proxy Server
echo ==========================================
echo   Reading configuration from .env file
echo.
echo   Casdoor: https://casdoor.mogulinker.com
echo   Backend: http://localhost:8501
echo   Port: 8080
echo ==========================================
echo.
cd /d "%~dp0"
.\conditioner-proxy.exe
