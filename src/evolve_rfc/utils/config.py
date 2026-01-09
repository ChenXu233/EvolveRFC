"""配置加载工具
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


def load_config(config_path: str = "config/workflow.yaml") -> Dict[str, Any]:
    """加载配置文件"""
    config_file = Path(config_path)

    if not config_file.exists():
        # 返回默认配置
        return get_default_config()

    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_default_config() -> Dict[str, Any]:
    """获取默认配置"""
    return {
        "routing": {
            "max_rounds": 10,
            "round_timeout_minutes": 30,
            "thresholds": {
                "deadlock_opposition_ratio": 0.3,
                "consensus_quorum": 0.8,
            },
        },
        "roles": {
            "architect": {"enabled": True, "must_speak": True},
            "security": {"enabled": True, "must_speak": True},
            "cost_control": {"enabled": True, "must_speak": True},
            "innovator": {"enabled": True, "must_speak": False},
        },
    }


def load_nightly_config(config_path: str = "config/nightly.yaml") -> Dict[str, Any]:
    """加载夜间守护进程配置"""
    config_file = Path(config_path)

    if not config_file.exists():
        return get_default_nightly_config()

    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def get_default_nightly_config() -> Dict[str, Any]:
    """获取默认夜间配置"""
    return {
        "nightly": {
            "trigger_hour": 0,
            "code_analysis": {
                "scope": "diff",
                "focus_dirs": ["src"],
            },
            "rfc_pre_discussion": {
                "enabled": True,
                "max_rfcs_per_night": 5,
            },
            "creative_proposal": {
                "enabled": True,
                "max_rounds": 5,
                "approval_threshold": "赞成>=2 且 赞成>反对",
                "daily_output_limit": 1,
            },
            "mode_weights": {
                "audit": 0.4,
                "pre_discussion": 0.3,
                "creative": 0.3,
            },
            "output": {
                "notify_on_empty": False,
                "max_output_per_night": 1,
            },
        },
    }


def is_github_action() -> bool:
    """检测是否在GitHub Action中运行"""
    return os.getenv("GITHUB_ACTIONS") == "true"
