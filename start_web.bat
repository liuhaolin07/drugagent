@echo off
chcp 65001 >nul
cd /d %~dp0
echo ==========================================
echo  DrugAgent v0.3 Web UI
echo  浏览器将打开 http://127.0.0.1:8077
echo  关闭本窗口即停止服务
echo ==========================================
start "" http://127.0.0.1:8077
.venv\Scripts\python.exe web.py
pause
