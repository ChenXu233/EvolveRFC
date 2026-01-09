"""夜间守护进程模式模块
"""

from .audit import run_audit_mode
from .discuss import run_discuss_mode
from .creative import run_creative_mode


def run_mode(mode: str, config: dict, output_dir: str):
    """运行指定模式

    Args:
        mode: 模式名称（audit, pre_discussion, creative）
        config: 完整配置
        output_dir: 输出目录
    """
    mode_handlers = {
        "audit": run_audit_mode,
        "pre_discussion": run_discuss_mode,
        "creative": run_creative_mode,
    }

    handler = mode_handlers.get(mode)
    if not handler:
        raise ValueError(f"未知模式: {mode}")

    handler(config, output_dir)


__all__ = [
    "run_mode",
    "run_audit_mode",
    "run_discuss_mode",
    "run_creative_mode",
]
