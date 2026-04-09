#!/bin/bash
# ClassFox 依赖安装脚本 (macOS)
# 用法: bash scripts/setup.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "=== ClassFox 开发环境配置 (macOS) ==="
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null; then
  echo "错误: 未找到 python3，请先安装 Python 3.10+"
  exit 1
fi
echo "✓ Python: $(python3 --version)"

# 检查 Node.js
if ! command -v node &>/dev/null; then
  echo "错误: 未找到 node，请先安装 Node.js 18+"
  exit 1
fi
echo "✓ Node.js: $(node --version)"

# 检查 Rust / Cargo (Tauri 构建依赖)
if ! command -v cargo &>/dev/null; then
  echo "警告: 未找到 cargo。Tauri 构建需要 Rust。安装: https://rustup.rs"
else
  echo "✓ Rust/Cargo: $(cargo --version)"
fi

echo ""

# 后端虚拟环境
echo "--- 配置后端 ---"
cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  echo "创建 Python 虚拟环境..."
  python3 -m venv .venv
fi
echo "安装后端依赖..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "✓ 后端依赖安装完成"

# 检查 .env
if [ ! -f ".env" ]; then
  echo ""
  echo "⚠ 未找到 backend/.env 文件。请先复制示例配置:"
  echo "  cp backend/.env.example backend/.env"
  echo ""
  echo "v1.1.1 默认建议先确认本地 Ollama 可用，并至少检查这些字段:"
  echo "  OLLAMA_BASE_URL=http://127.0.0.1:11434"
  echo "  OLLAMA_CHAT_MODEL=qwen2.5:1.5b"
  echo "  OLLAMA_FINAL_SUMMARY_MODEL=gemma4:e4b"
  echo "  ASR_MODE=local   # 可选: local / mock / dashscope / seed-asr"
  echo ""
  echo "首次使用本地推理前建议执行:"
  echo "  ollama pull qwen2.5:1.5b"
  echo "  ollama pull gemma4:e4b"
fi

echo ""

# 前端依赖
echo "--- 配置前端 ---"
cd "$FRONTEND_DIR"
echo "安装前端依赖..."
npm install --silent
echo "✓ 前端依赖安装完成"

echo ""
echo "=== 配置完成 ==="
echo ""
echo "启动开发环境:"
echo "  bash scripts/dev.sh"
echo ""
echo "仅启动后端:"
echo "  bash scripts/start_backend.sh"
