#!/bin/bash
# ClassFox 后端启动脚本 (macOS)
# 用法: bash scripts/start_backend.sh

set -e

BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
cd "$BACKEND_DIR"

VENV_PYTHON=".venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
  echo "虚拟环境未找到，请先运行: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

echo "启动 ClassFox 后端服务 (http://127.0.0.1:8765) ..."
"$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload
