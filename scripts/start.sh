#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if ! command -v docker >/dev/null 2>&1; then
  echo '请先安装并启动 Docker Desktop（Linux 可使用 Docker Engine + Compose）。' >&2
  exit 1
fi
docker compose version >/dev/null
docker compose up -d --build --wait --wait-timeout 120
published="$(docker compose port drugagent 8077)"
port="${published##*:}"
echo "DrugAgent 已启动：http://localhost:$port"
echo '首次完整分析需在 .env 中配置 GLM_API_KEY 或 DEEPSEEK_API_KEY，再重新运行本脚本。'
