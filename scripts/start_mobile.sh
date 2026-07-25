#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

command -v cloudflared >/dev/null 2>&1 \
  || { printf '[mobile] 错误：未找到 cloudflared，请先执行：brew install cloudflared\n' >&2; exit 1; }
[[ -x .venv/bin/python ]] \
  || { printf '[mobile] 错误：Python 环境尚未安装，请先执行：make setup\n' >&2; exit 1; }

exec .venv/bin/python scripts/start_mobile.py
