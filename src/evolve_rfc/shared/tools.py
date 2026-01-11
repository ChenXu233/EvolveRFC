"""LangChain 工具定义 - 集成 MCP 工具

将 MCP 工具转换为 LangChain Tools，供智能体在多段思考中调用。
"""

from pathlib import Path
import re
import json
from typing import List, Optional, Dict, Any
from contextvars import ContextVar
from dataclasses import dataclass, field

from langchain_core.tools import tool


# === 数据结构 ===

@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    result: str = ""
    timestamp: float = field(default_factory=lambda: __import__("time").time())


# === 上下文变量用于工具间共享数据 ===
_viewpoints_from_tool: ContextVar[Optional[List[dict]]] = ContextVar(
    "viewpoints_from_tool", default=None
)

_tool_call_history: ContextVar[Optional[List[ToolCallRecord]]] = ContextVar(
    "tool_call_history", default=None
)


def get_viewpoints_from_tool() -> List[dict]:
    """获取通过工具调用添加的观点"""
    result = _viewpoints_from_tool.get()
    return result if result is not None else []


def clear_viewpoints_from_tool():
    """清空通过工具调用添加的观点"""
    _viewpoints_from_tool.set(None)


def get_tool_call_history() -> List[ToolCallRecord]:
    """获取工具调用历史"""
    result = _tool_call_history.get()
    return result if result is not None else []


def clear_tool_call_history():
    """清空工具调用历史"""
    _tool_call_history.set(None)


def record_tool_call(tool_name: str, arguments: Dict[str, Any], result: str = ""):
    """记录工具调用"""
    history = get_tool_call_history()
    history.append(ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments,
        result=result,
    ))
    _tool_call_history.set(history)


# === 使用 @tool 装饰器定义工具 ===

@tool
def file_read(file_path: str, limit: int = 10000, **kwargs) -> str:
    """读取文件内容，用于获取代码、文档等信息

    Args:
        file_path: 要读取的文件路径
        limit: 最大读取字符数（默认10000）
    """
    # 忽略未知参数
    if kwargs:
        pass

    if not file_path or not isinstance(file_path, str):
        return "错误: file_path 参数必须是非空字符串"

    path = Path(file_path)
    if not path.exists():
        return f"文件不存在: {file_path}"

    if path.is_dir():
        return f"错误: {file_path} 是目录，不是文件"

    # 限制读取大小，防止内存问题
    try:
        file_size = path.stat().st_size
        if file_size > 5 * 1024 * 1024:  # 5MB 限制
            return f"错误: 文件过大 ({file_size / 1024 / 1024:.1f}MB)，无法读取"

        content = path.read_text(encoding="utf-8")
        if len(content) > limit:
            content = content[:limit] + f"\n\n... (共 {len(content)} 字符，已截断)"

        return content
    except UnicodeDecodeError:
        return f"错误: 无法解码文件 {file_path}，请尝试其他编码"
    except PermissionError:
        return f"错误: 没有权限读取文件 {file_path}"
    except Exception as e:
        return f"读取文件出错: {str(e)}"


@tool
def file_search(start_dir: str = ".", pattern: str = "*", max_count: int = 50, **kwargs) -> str:
    """递归查找文件，支持 glob 模式匹配

    Args:
        start_dir: 起始目录（默认当前目录）
        pattern: 文件匹配模式 (如 "*.py", "*.md")
        max_count: 最大返回数量
    """
    # 忽略未知参数
    if kwargs:
        pass

    # 验证参数
    if not start_dir or not isinstance(start_dir, str):
        return "错误: start_dir 参数无效"

    path = Path(start_dir)
    if not path.exists():
        return f"目录不存在: {start_dir}"

    if not path.is_dir():
        return f"路径不是目录: {start_dir}"

    # 限制 max_count 防止资源耗尽
    max_count = min(max_count, 100)

    files = []
    try:
        for p in path.rglob(pattern):
            if p.is_file():
                files.append(str(p))
                if len(files) >= max_count:
                    break
    except Exception as e:
        return f"搜索出错: {str(e)}"

    if not files:
        return "未找到匹配的文件"

    return f"找到 {len(files)} 个文件:\n" + "\n".join(f"- {f}" for f in files)


@tool
def code_search(pattern: str, file_pattern: str = "*.py", max_count: int = 20, **kwargs) -> str:
    """在代码文件中搜索正则表达式，返回匹配位置和上下文

    Args:
        pattern: 搜索的正则表达式
        file_pattern: 文件匹配模式 (如 "*.py", "*.md")
        max_count: 最大返回结果数
    """
    # 过滤掉未知参数
    if kwargs:
        pass  # 忽略未知参数

    # 检查 pattern 是否为空或无效
    if not pattern or not isinstance(pattern, str):
        return "错误: pattern 参数必须是非空字符串"

    # 清理 pattern（去除可能的注释）
    pattern = pattern.strip()
    if pattern.startswith('#'):
        return "错误: pattern 不能以 # 开头"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"正则表达式错误: {e}"

    matches = []
    for p in Path(".").rglob(file_pattern):
        if p.is_file() and p.stat().st_size < 500000:  # 跳过超大文件
            try:
                content = p.read_text(encoding="utf-8")
                for match in regex.finditer(content):
                    matches.append({
                        "file": str(p),
                        "line": content[:match.start()].count("\n") + 1,
                        "match": match.group()[:100]
                    })
                    if len(matches) >= max_count:
                        break
            except Exception:
                continue

        if len(matches) >= max_count:
            break

    if not matches:
        return "未找到匹配"

    result = [f"找到 {len(matches)} 个匹配:"]
    for m in matches[:10]:
        result.append(f"  {m['file']}:{m['line']} - {m['match']}")

    if len(matches) > 10:
        result.append(f"  ... 还有 {len(matches) - 10} 个匹配")

    return "\n".join(result)


@tool
def list_dir(dir_path: str = ".", pattern: str = "*", max_count: int = 50, **kwargs) -> str:
    """列出目录下的文件和子目录

    Args:
        dir_path: 目录路径（默认当前目录）
        pattern: 文件匹配模式（默认所有文件）
        max_count: 最大返回数量
    """
    # 忽略未知参数
    if kwargs:
        pass

    if not dir_path or not isinstance(dir_path, str):
        return "错误: dir_path 参数无效"

    path = Path(dir_path)
    if not path.exists():
        return f"目录不存在: {dir_path}"

    if not path.is_dir():
        return f"错误: {dir_path} 不是目录"

    # 限制 max_count
    max_count = min(max_count, 100)

    items = []
    try:
        for p in path.glob(pattern):
            if p.is_dir():
                items.append(f"[DIR] {p.name}/")
            else:
                size_info = ""
                try:
                    size = p.stat().st_size
                    if size > 1024:
                        size_info = f" ({size // 1024}KB)"
                except Exception:
                    pass
                items.append(f"[FILE] {p.name}{size_info}")

            if len(items) >= max_count:
                items = items[:max_count]
                items.append(f"... (共 {len(items)} 项，已截断)")
                break
    except Exception as e:
        return f"列出目录出错: {str(e)}"

    if not items:
        return f"目录 {dir_path} 中没有匹配的文件"

    return f"目录 {dir_path}:\n" + "\n".join(items)


@tool
def propose_viewpoint(
    content: str,
    evidence: List[str],
    stance: str,
    **kwargs,
) -> str:
    """提出一个新观点到观点池。

    使用此工具当你发现了一个值得讨论的新问题或设计方案时。
    观点池最多容纳3个活跃观点，只有当观点被多数人赞成（投票解决）后，才能提出新观点。

    Args:
        content: 观点内容（一句话概括核心问题）
        evidence: 支撑论据列表（最多3个）
        stance: 你的立场 ("赞成" | "反对" | "弃权")
    """
    # 忽略未知参数
    if kwargs:
        pass

    # 验证 content
    if not content or not isinstance(content, str):
        return "错误: content 必须是字符串类型"

    if len(content.strip()) < 5:
        return "错误: content 内容太短，请提供更详细的问题描述"

    # 检查是否超过限制
    current = _viewpoints_from_tool.get() or []
    if len(current) >= 3:
        return "观点池已满（最多3个观点），不能提出新观点。请先回应现有观点，或等待观点被解决。"

    # 验证立场
    if stance not in ["赞成", "反对", "弃权"]:
        return "立场必须是以下之一：赞成、反对、弃权"

    # 验证论据
    if not isinstance(evidence, list) or len(evidence) == 0:
        return "论据必须是列表格式，例如：[\"论据1\", \"论据2\"]"

    viewpoint = {
        "content": content,
        "evidence": evidence[:3],  # 最多3个论据
        "stance": stance,
    }

    _viewpoints_from_tool.set(current + [viewpoint])

    # 记录工具调用
    record_tool_call("propose_viewpoint", {
        "content": content,
        "evidence": evidence,
        "stance": stance,
    }, f"观点已添加到观点池：{content[:50]}...")

    return f"观点已添加到观点池：{content[:50]}...（当前池中 {len(current) + 1}/3 个观点）"


@tool
def respond_to_viewpoint(
    viewpoint_id: str,
    response: str,
    stance: str,
    **kwargs,
) -> str:
    """回应观点池中的已有观点。

    使用此工具对现有观点表达支持或反对，并说明理由。
    每个观点需要至少获得2票赞成且赞成票 > 反对票 才能解决。

    Args:
        viewpoint_id: 要回应的观点ID
        response: 你的回应内容（支持/反对/补充理由）
        stance: 你对该观点的立场 ("赞成" | "反对" | "弃权")
    """
    # 忽略未知参数
    if kwargs:
        pass

    # 验证参数
    if not viewpoint_id or not isinstance(viewpoint_id, str):
        return "错误: viewpoint_id 必须是字符串"

    if not response or not isinstance(response, str):
        return "错误: response 必须是字符串"

    if len(response.strip()) < 3:
        return "错误: response 内容太短，请提供更详细的理由"

    # 验证立场
    if stance not in ["赞成", "反对", "弃权"]:
        return "立场必须是以下之一：赞成、反对、弃权"

    # 记录回应（通过 JSON 存储在响应中，供后续解析）
    response_data = {
        "type": "viewpoint_response",
        "viewpoint_id": viewpoint_id,
        "response": response,
        "stance": stance,
    }

    # 记录工具调用
    record_tool_call("respond_to_viewpoint", {
        "viewpoint_id": viewpoint_id,
        "response": response,
        "stance": stance,
    }, json.dumps(response_data, ensure_ascii=False))

    return json.dumps(response_data, ensure_ascii=False)


# === 工具列表 ===

def get_all_tools() -> list:
    """获取所有可用的工具列表"""
    return [
        file_read,
        file_search,
        code_search,
        list_dir,
        propose_viewpoint,
        respond_to_viewpoint,
    ]


def get_tool_names() -> list[str]:
    """获取所有工具名称"""
    return [t.name for t in get_all_tools()]


# === 清理工具 ===

def cleanup_tool_context():
    """清理工具调用上下文（防止数据残留）
    
    在每次工具调用会话开始前调用，确保上下文干净。
    """
    clear_viewpoints_from_tool()
    clear_tool_call_history()
