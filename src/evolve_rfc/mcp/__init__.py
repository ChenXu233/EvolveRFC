"""EvolveRFC MCP Server

提供 RFC 评审相关的工具，让其他 AI 助手可以调用 EvolveRFC 的功能。

Available Tools:
    - read_rfc: 读取 RFC 文件内容
    - list_rfcs: 列出所有 RFC 文件
    - read_code: 读取代码文件内容
    - list_code_files: 列出代码文件
    - get_config: 获取配置值
    - get_role_prompt: 获取角色提示词
    - analyze_code_quality: 快速分析代码质量
"""

from .server import MCPTools

__all__ = ["MCPTools"]
