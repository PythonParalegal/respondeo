@echo off
echo ============================================================
echo  DIY eDiscovery Hub - Launching Platform
echo ============================================================
echo.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Starting Streamlit...
streamlit run home.py --server.address 0.0.0.0 --server.port 8501
