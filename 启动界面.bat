@echo off
rem Double-click to start the assistant UI (LAN accessible)
cd /d %~dp0
echo ============================================
echo  Browser:  http://localhost:8501
echo  Phone (same Wi-Fi):  http://192.168.8.245:8501
echo  (If phone cannot connect, run the firewall
echo   command once in ADMIN PowerShell, see README)
echo ============================================
streamlit run app/main.py --server.address 0.0.0.0 --server.port 8501 --server.runOnSave true
pause
