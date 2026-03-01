@echo off
echo ==========================================
echo   Starting Streamlit Backend
echo ==========================================
echo   Port: 8501
echo   URL: http://localhost:8501
echo ==========================================
echo.
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
