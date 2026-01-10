"""EvolveRFC MCP Server

提供文件操作工具，让其他 AI 助手可以读取文件和搜索代码。

Available Tools:
    - read: 读取文件内容
    - read_regex: 读取文件并用正则过滤内容
    - list: 列出目录下的文件
    - list_regex: 列出目录下的文件（用正则过滤）
    - find: 按模式查找文件
    - find_regex: 按正则查找文件
"""
import re
from pathlib import Path


class MCPTools:
    """MCP 工具类 - 提供给 MCP Server 调用的工具集合"""

    @staticmethod
    def read(file_path: str, limit: int = 10000) -> str:
        """读取文件内容

        Args:
            file_path: 文件路径
            limit: 最大读取字符数

        Returns:
            文件内容
        """
        path = Path(file_path)
        if not path.exists():
            return f"文件不存在: {file_path}"

        content = path.read_text(encoding="utf-8")
        if len(content) > limit:
            content = content[:limit] + f"\n\n... (共 {len(content)} 字符，已截断)"

        return content

    @staticmethod
    def read_regex(file_path: str, pattern: str, first_match: bool = False) -> str:
        """读取文件并用正则过滤内容

        Args:
            file_path: 文件路径
            pattern: 正则表达式
            first_match: 只返回第一个匹配块

        Returns:
            匹配的内容
        """
        content = MCPTools.read(file_path)
        if content.startswith("文件不存在"):
            return content

        try:
            regex = re.compile(pattern, re.MULTILINE)
            matches = list(regex.finditer(content))

            if not matches:
                return "未找到匹配内容"

            if first_match:
                match = matches[0]
                return content[match.start():match.end()]

            # 返回所有匹配及其上下文
            result = []
            for i, match in enumerate(matches):
                start, end = match.span()
                # 包含前后各2行上下文
                lines = content[:start].split("\n")
                context_start = max(0, len(lines) - 3)
                context = "\n".join(lines[context_start:])
                result.append(f"--- 匹配 {i + 1} ---\n{context}{content[start:end]}")

            return "\n".join(result)

        except re.error as e:
            return f"正则表达式错误: {e}"

    @staticmethod
    def list(
        dir_path: str = ".",
        pattern: str = "*",
        max_count: int = 50
    ) -> str:
        """列出目录下的文件

        Args:
            dir_path: 目录路径
            pattern: 文件匹配模式 (如 *.py, *.md)
            max_count: 最大返回数量

        Returns:
            文件列表
        """
        path = Path(dir_path)
        if not path.exists() or not path.is_dir():
            return f"目录不存在: {dir_path}"

        files = []
        for p in path.glob(pattern):
            if p.is_file():
                rel_path = str(p.relative_to(path.parent))
                files.append(rel_path)
                if len(files) >= max_count:
                    break

        if not files:
            return f"目录 {dir_path} 中没有匹配的文件"

        return f"文件列表 (共 {len(files)} 个):\n" + "\n".join(f"- {f}" for f in files)

    @staticmethod
    def list_regex(
        dir_path: str = ".",
        pattern: str = ".*",
        max_count: int = 50
    ) -> str:
        """列出目录下的文件（用正则过滤文件名）

        Args:
            dir_path: 目录路径
            pattern: 文件名正则表达式
            max_count: 最大返回数量

        Returns:
            匹配的文件列表
        """
        path = Path(dir_path)
        if not path.exists() or not path.is_dir():
            return f"目录不存在: {dir_path}"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"正则表达式错误: {e}"

        files = []
        for p in path.rglob("*"):
            if p.is_file():
                rel_path = str(p.relative_to(path.parent))
                if regex.search(rel_path):
                    files.append(rel_path)
                    if len(files) >= max_count:
                        break

        if not files:
            return f"目录 {dir_path} 中没有匹配的文件"

        return f"文件列表 (共 {len(files)} 个):\n" + "\n".join(f"- {f}" for f in files)

    @staticmethod
    def find(
        start_dir: str = ".",
        pattern: str = "*",
        max_count: int = 50
    ) -> str:
        """递归查找文件

        Args:
            start_dir: 起始目录
            pattern: 文件匹配模式
            max_count: 最大返回数量

        Returns:
            找到的文件列表
        """
        path = Path(start_dir)
        if not path.exists():
            return f"目录不存在: {start_dir}"

        files = []
        for p in path.rglob(pattern):
            if p.is_file():
                files.append(str(p))
                if len(files) >= max_count:
                    break

        if not files:
            return "未找到匹配的文件"

        return f"找到 {len(files)} 个文件:\n" + "\n".join(f"- {f}" for f in files)

    @staticmethod
    def find_regex(
        start_dir: str = ".",
        pattern: str = ".*",
        max_count: int = 50
    ) -> str:
        """递归查找文件（用正则过滤路径）

        Args:
            start_dir: 起始目录
            pattern: 路径正则表达式
            max_count: 最大返回数量

        Returns:
            匹配的文件列表
        """
        path = Path(start_dir)
        if not path.exists():
            return f"目录不存在: {start_dir}"

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"正则表达式错误: {e}"

        files = []
        for p in path.rglob("*"):
            if p.is_file():
                str_path = str(p)
                if regex.search(str_path):
                    files.append(str_path)
                    if len(files) >= max_count:
                        break

        if not files:
            return "未找到匹配的文件"

        return f"找到 {len(files)} 个文件:\n" + "\n".join(f"- {f}" for f in files)
