#!/bin/bash
# ClassFox 开发环境一键启动 (macOS)
# 同时启动后端 FastAPI 和前端 Tauri 开发服务器
# 用法: bash scripts/dev.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# 启动后端
echo "▶ 启动后端 (FastAPI)..."
VENV_PYTHON="$BACKEND_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
  echo "错误: 虚拟环境未找到。请先运行:"
  echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$BACKEND_DIR"
"$VENV_PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8765 --reload &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID"

# 等待后端就绪
echo "  等待后端就绪..."
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:8765/api/health > /dev/null 2>&1; then
    echo "  ✓ 后端已就绪"
    break
  fi
  sleep 1
done

# 启动前端 Tauri
echo "▶ 启动前端 (Tauri + React)..."
cd "$FRONTEND_DIR"
npm run tauri dev &
FRONTEND_PID=$!
echo "  前端 PID: $FRONTEND_PID"

echo ""
echo "ClassFox 开发服务已启动。按 Ctrl+C 停止所有服务。"
echo ""

# 捕获退出信号，关闭后台进程
cleanup() {
  echo ""
  echo "正在停止服务..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait
  echo "已停止。"
}
trap cleanup INT TERM

wait
