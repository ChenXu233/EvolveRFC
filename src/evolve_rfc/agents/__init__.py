"""智能体模块 - 角色提示词与智能体实现
"""

from .base import BaseAgent
from .roles import RoleType, get_role_prompt, get_active_roles, get_reviewer_roles, is_voter
from .clerk import ClerkAgent

__all__ = [
    "BaseAgent",
    "RoleType",  # 类型别名: str
    "get_role_prompt",
    "get_active_roles",
    "get_reviewer_roles",
    "is_voter",
    "ClerkAgent",
]
