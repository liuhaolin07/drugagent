@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where docker >nul 2>nul
if errorlevel 1 (
  echo 请先安装并启动 Docker Desktop。
  pause
  exit /b 1
)
docker compose version >nul 2>nul
if errorlevel 1 (
  echo Docker Compose 不可用，请更新 Docker Desktop。
  pause
  exit /b 1
)
docker compose up -d --build --wait --wait-timeout 120
if errorlevel 1 (
  echo 启动失败，请查看上方错误。可运行 docker compose logs --tail 100 检查服务日志。
  pause
  exit /b 1
)
set "DRUGAGENT_BROWSER_PORT=8077"
for /f "tokens=2 delims=:" %%P in ('docker compose port drugagent 8077') do set "DRUGAGENT_BROWSER_PORT=%%P"
echo DrugAgent 已启动：http://localhost:%DRUGAGENT_BROWSER_PORT%
echo 完整分析需要在 .env 配置模型密钥，修改后再次运行本脚本即可。
start "" http://localhost:%DRUGAGENT_BROWSER_PORT%
pause
