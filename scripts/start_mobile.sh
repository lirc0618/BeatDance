#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8000}"
ORIGIN="http://127.0.0.1:${PORT}"
HEALTH_URL="${ORIGIN}/api/v1/health"
BACKEND_PID=""
TUNNEL_PID=""

log() {
  printf '[mobile] %s\n' "$1"
}

fail() {
  printf '[mobile] 错误：%s\n' "$1" >&2
  exit 1
}

cleanup() {
  exit_code=$?
  trap - EXIT INT TERM HUP

  if [[ -n "${TUNNEL_PID}" ]] && kill -0 "${TUNNEL_PID}" 2>/dev/null; then
    kill "${TUNNEL_PID}" 2>/dev/null || true
    wait "${TUNNEL_PID}" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    log "正在停止本次启动的后端服务…"
    kill "${BACKEND_PID}" 2>/dev/null || true
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

trap cleanup EXIT INT TERM HUP

cd "${PROJECT_DIR}"

command -v cloudflared >/dev/null 2>&1 \
  || fail "未找到 cloudflared，请先执行：brew install cloudflared"
command -v curl >/dev/null 2>&1 || fail "未找到 curl"
[[ -x .venv/bin/uvicorn ]] || fail "Python 环境尚未安装，请先执行：make setup"

if curl --fail --silent --show-error --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
  log "检测到 ${ORIGIN} 已有可用后端，将直接复用。"
else
  log "正在启动后端：${ORIGIN}"
  mkdir -p data
  DATA_DIR="${PROJECT_DIR}/data" \
  H5_DIR="${PROJECT_DIR}/h5" \
  FEED_DIR="${PROJECT_DIR}/data/feeds" \
  SEED_FEED_DIR="${PROJECT_DIR}/assets/samples/open_sources" \
  SEED_REFERENCE_DIR="${PROJECT_DIR}/assets/references" \
  TUTORIAL_ASSETS_DIR="${PROJECT_DIR}/assets/tutorials" \
  ALLOW_INSECURE_ADMIN_TOKEN=true \
  PUBLIC_BASE_URL="${ORIGIN}" \
    .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port "${PORT}" &
  BACKEND_PID=$!

  for _ in $(seq 1 80); do
    if curl --fail --silent --show-error --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      wait "${BACKEND_PID}" || true
      fail "后端启动失败，请检查上方日志。"
    fi
    sleep 0.25
  done

  curl --fail --silent --show-error --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1 \
    || fail "后端健康检查超时：${HEALTH_URL}"
  log "后端健康检查通过。"
fi

log "正在创建 Cloudflare 临时 HTTPS 地址…"
log "请在下方日志中找到 https://*.trycloudflare.com，并用手机打开其 /app/ 路径。"
log "按 Ctrl+C 会关闭隧道，并停止本命令启动的后端。"

cloudflared tunnel --url "${ORIGIN}" --no-autoupdate &
TUNNEL_PID=$!
wait "${TUNNEL_PID}"
