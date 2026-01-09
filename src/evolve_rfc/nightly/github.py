"""GitHub Action模式支持
"""

import os
from typing import Dict, Any
from pathlib import Path

from .daemon import DaemonConfig, RunMode
from .modes import run_mode
from ..utils.config import load_nightly_config


def run_github_workflow(config: DaemonConfig):
    """运行GitHub Action工作流"""
    print("🚀 启动GitHub Action模式...")

    # 加载完整配置
    full_config = load_nightly_config(config.config_path)

    # 获取模式（从输入或随机）
    mode_input = os.getenv("GITHUB_INPUT_MODE", "")
    if mode_input and mode_input != "random":
        selected_mode = mode_input
    else:
        # 随机选择模式
        mode_weights = full_config.get("nightly", {}).get("mode_weights", {})
        selected_mode = _select_mode(mode_weights)

    print(f"📊 选择模式: {selected_mode}")

    # 执行夜间工作流
    run_mode(selected_mode, full_config, config.output_dir)

    # 检查输出
    output_files = list(Path(config.output_dir).glob("*.md"))

    if output_files:
        # 设置GitHub Action输出
        latest_file = max(output_files, key=lambda p: p.stat().st_mtime)
        print(f"output_file={latest_file}")
        print(f"output_content=$(cat {latest_file} | head -c 200)...")
    else:
        print("📭 当日无输出（静默结束）")


def _select_mode(weights: dict) -> str:
    """根据权重选择运行模式"""
    import random

    if not weights:
        return "audit"

    modes = list(weights.keys())
    values = list(weights.values())
    total = sum(values)

    if total == 0:
        return modes[0]

    r = random.random() * total
    cumsum = 0

    for mode, weight in zip(modes, values):
        cumsum += weight
        if r <= cumsum:
            return mode

    return modes[0]


def create_pull_request_if_needed():
    """如有输出，创建Pull Request（由Action调用）"""
    # 此函数由 create-pull-request Action 调用
    pass
