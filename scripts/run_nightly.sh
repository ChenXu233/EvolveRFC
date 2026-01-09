#!/bin/bash
# 夜间守护进程启动脚本（本地模式）

export MINIMAX_API_KEY="${MINIMAX_API_KEY}"
export MINIMAX_BASE_URL="${MINIMAX_BASE_URL:-https://api.minimax.chat}"

# 检查必需的环境变量
if [ -z "$MINIMAX_API_KEY" ]; then
    echo "❌ 错误：请设置 MINIMAX_API_KEY 环境变量"
    exit 1
fi

# 进入项目目录
cd "$(dirname "$0")/.."

# 运行守护进程
echo "🚀 启动夜间守护进程（本地模式）..."
uv run python -m evolve_rfc.nightly.daemon --config config/nightly.yaml
