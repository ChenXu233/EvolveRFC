"""智能体模块 - 角色提示词与智能体实现
"""

from .base import BaseAgent
from .roles import RoleType, get_role_prompt
from .clerk import ClerkAgent

__all__ = [
    "BaseAgent",
    "RoleType",
    "get_role_prompt",
    "ClerkAgent",
]
