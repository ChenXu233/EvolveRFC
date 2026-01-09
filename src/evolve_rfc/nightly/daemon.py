"""夜间守护进程主入口
"""

import argparse
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from ..utils.config import load_nightly_config, is_github_action


class RunMode(Enum):
    """运行模式"""
    LOCAL = "local"
    GITHUB = "github"


@dataclass
class DaemonConfig:
    """守护进程配置"""
    mode: RunMode
    config_path: str = "config/nightly.yaml"
    output_dir: str = "nightly_output"
    notify: bool = True
    config: dict = field(default_factory=dict)


def parse_args() -> DaemonConfig:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="EvolveRFC 夜间守护进程")

    parser.add_argument(
        "--mode",
        choices=["local", "github"],
        default="local",
        help="运行模式：本地或GitHub Action",
    )
    parser.add_argument(
        "--config",
        default="config/nightly.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--output",
        default="nightly_output",
        help="输出目录",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="禁用通知",
    )

    args = parser.parse_args()

    # 自动检测运行模式
    mode = RunMode(args.mode)
    if mode == RunMode.LOCAL and is_github_action():
        mode = RunMode.GITHUB

    # 加载配置
    config = load_nightly_config(args.config)

    return DaemonConfig(
        mode=mode,
        config_path=args.config,
        output_dir=args.output,
        notify=not args.no_notify,
        config=config,
    )


def run_local_mode(config: DaemonConfig):
    """本地模式运行"""
    from .modes import run_mode as run_nightly_mode
    from ..utils.config import load_nightly_config

    print(f"🚀 启动夜间守护进程（本地模式）...")
    print(f"📁 输出目录: {config.output_dir}")

    # 确保输出目录存在
    Path(config.output_dir).mkdir(parents=True, exist_ok=True)

    # 加载完整配置
    full_config = load_nightly_config(config.config_path)

    # 选择运行模式
    mode_weights = full_config.get("nightly", {}).get("mode_weights", {})
    selected_mode = _select_mode(mode_weights)

    print(f"📊 选择模式: {selected_mode}")

    # 执行夜间工作流
    run_nightly_mode(selected_mode, full_config, config.output_dir)

    print("✅ 夜间守护进程执行完成")


def run_github_mode(config: DaemonConfig):
    """GitHub Action模式运行"""
    from .github import run_github_workflow

    print(f"🚀 启动夜间守护进程（GitHub Action模式）...")

    # 执行GitHub工作流
    run_github_workflow(config)


def _select_mode(weights: dict) -> str:
    """根据权重选择运行模式（简化实现）"""
    import random

    if not weights:
        return "audit"

    # 随机选择
    modes = list(weights.keys())
    values = list(weights.values())
    total = sum(values)

    if total == 0:
        return modes[0]

    # 加权随机选择
    r = random.random() * total
    cumsum = 0

    for mode, weight in zip(modes, values):
        cumsum += weight
        if r <= cumsum:
            return mode

    return modes[0]


def main():
    """主入口"""
    config = parse_args()

    if config.mode == RunMode.GITHUB:
        run_github_mode(config)
    else:
        run_local_mode(config)


if __name__ == "__main__":
    main()
