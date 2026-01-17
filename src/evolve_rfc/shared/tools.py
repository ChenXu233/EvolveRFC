"""LangChain 工具定义 - 集成 MCP 工具

将 MCP 工具转换为 LangChain Tools，供智能体在多段思考中调用。
"""

from pathlib import Path
import re
import json
from typing import List, Optional, Dict, Any, Callable
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


# === 全局变量用于工具间共享数据（单线程顺序执行，直接用全局变量） ===
_viewpoints_from_tool: List[dict] = []

_tool_call_history: List[ToolCallRecord] = []

_viewpoint_pool_for_tool: List = []

_current_role_for_tool: Optional[str] = None
_role_viewpoint_counts: Dict[str, int] = {}

_tool_invoke_callback: Optional[Callable[[str, Dict, str], None]] = None


def set_tool_invoke_callback(callback: Optional[Callable[[str, Dict, str], None]]):
    """设置工具调用回调，用于实时显示工具调用"""
    global _tool_invoke_callback
    _tool_invoke_callback = callback


def notify_tool_invoke(tool_name: str, arguments: Dict[str, Any], result: str = ""):
    """通知工具被调用（用于实时显示）"""
    global _tool_invoke_callback
    if _tool_invoke_callback:
        try:
            _tool_invoke_callback(tool_name, arguments, result)
        except Exception:
            pass


def get_viewpoints_from_tool() -> List[dict]:
    """获取通过工具调用添加的观点（默认返回当前角色的观点）"""
    if _current_role_for_tool:
        return [
            vp
            for vp in _viewpoints_from_tool
            if vp.get("proposer") == _current_role_for_tool
        ]
    return _viewpoints_from_tool


def clear_viewpoints_from_tool():
    """清空当前工具会话的观点缓存（每个角色独立）"""
    global _viewpoints_from_tool
    _viewpoints_from_tool = []


def get_tool_call_history() -> List[ToolCallRecord]:
    """获取工具调用历史"""
    return _tool_call_history


def clear_tool_call_history():
    """清空工具调用历史"""
    global _tool_call_history
    _tool_call_history = []


def record_tool_call(tool_name: str, arguments: Dict[str, Any], result: str = ""):
    """记录工具调用"""
    global _tool_call_history
    _tool_call_history.append(ToolCallRecord(
        tool_name=tool_name,
        arguments=arguments,
        result=result,
    ))


# === 观点池上下文管理 ===
def set_viewpoint_pool_for_tool(pool: list):
    """设置当前观点池，供工具读取"""
    global _viewpoint_pool_for_tool
    _viewpoint_pool_for_tool = pool


def get_viewpoint_pool_for_tool() -> list:
    """获取工具视角的观点池"""
    return _viewpoint_pool_for_tool


def clear_viewpoint_pool_for_tool():
    """清空工具视角的观点池"""
    global _viewpoint_pool_for_tool
    _viewpoint_pool_for_tool = []


# === 角色上下文管理 ===
def set_current_role_for_tool(role: str):
    """设置当前工具调用所属角色"""
    global _current_role_for_tool
    _current_role_for_tool = role
    if role not in _role_viewpoint_counts:
        _role_viewpoint_counts[role] = 0


def clear_role_context_for_tool():
    """清空角色上下文（用于每次角色评审开始前重置）"""
    global _current_role_for_tool, _role_viewpoint_counts
    _current_role_for_tool = None
    _role_viewpoint_counts = {}


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
def get_viewpoint_pool(**kwargs) -> str:
    """查看当前观点池的状态，包括所有活跃观点、投票情况和历史回应。

    返回当前观点池的完整信息，用于了解还有哪些观点需要回应。
    """
    # 忽略未知参数
    if kwargs:
        pass

    from ..core.state import ViewpointStatus

    pool = _viewpoint_pool_for_tool
    if not pool:
        return "观点池为空，没有活跃观点。你可以提出新观点。"

    result = ["=== 当前观点池 ==="]
    result.append(f"共 {len(pool)} 个活跃观点（最多3个）\n")

    for i, vp in enumerate(pool, 1):
        status_icon = "🔴" if vp.status == ViewpointStatus.ACTIVE else "🟢"
        votes = vp.vote_count
        votes_str = f"👍{votes.get('赞成', 0)} 👎{votes.get('反对', 0)} 🤔{votes.get('弃权', 0)}"

        result.append(f"{status_icon} 观点 {i} [{vp.id}]")
        result.append(f"   内容: {vp.content}")
        result.append(f"   提出者: {vp.proposer} | 投票: {votes_str}")

        # 显示论据
        if vp.evidence:
            result.append(f"   论据: {'; '.join(vp.evidence[:2])}")

        # 显示回应历史
        if vp.arguments:
            result.append(f"   已有 {len(vp.arguments)} 条回应:")
            for arg in vp.arguments[-3:]:  # 最近3条
                stance_icon = "👍" if arg.get("stance") == "赞成" else "👎" if arg.get("stance") == "反对" else "🤔"
                result.append(f"     {stance_icon} {arg.get('actor', '?')}: {arg.get('content', '')[:80]}")

        result.append("")  # 空行

    result.append("=== 操作提示 ===")
    result.append("- 必须先回应所有观点，才能提出新观点")
    result.append("- 每个观点需要至少2票赞成且赞成>反对才能解决")
    result.append("- 每人每轮最多提出1个新观点")

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

    规则：
    - 每人每轮最多提出1个新观点
    - 观点池最多3个活跃观点
    - 必须先回应现有观点，才能提出新观点

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

    # 检查每个角色是否超过限制（每人每轮最多1个）
    global _viewpoints_from_tool
    role_name = _current_role_for_tool or "unknown"
    if _role_viewpoint_counts.get(role_name, 0) >= 1:
        return "错误: 每个角色每轮最多提出1个新观点"

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
        "proposer": role_name,
    }

    _viewpoints_from_tool = _viewpoints_from_tool + [viewpoint]
    _role_viewpoint_counts[role_name] = _role_viewpoint_counts.get(role_name, 0) + 1

    # 记录工具调用
    record_tool_call("propose_viewpoint", {
        "content": content,
        "evidence": evidence,
        "stance": stance,
    }, f"观点已添加到观点池：{content[:50]}...")

    # 实时通知工具调用
    notify_tool_invoke("propose_viewpoint", {
        "content": content,
        "evidence": evidence,
        "stance": stance,
    }, f"观点已添加：{content[:50]}...")

    return f"观点已添加到观点池：{content[:50]}...（当前角色本轮已提出 {_role_viewpoint_counts[role_name]}/1 个观点）"


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

    # 实时通知工具调用
    notify_tool_invoke("respond_to_viewpoint", {
        "viewpoint_id": viewpoint_id,
        "response": response,
        "stance": stance,
    }, f"回应观点 {viewpoint_id}: {stance}")

    return json.dumps(response_data, ensure_ascii=False)


# === 工具列表 ===

def get_all_tools() -> list:
    """获取所有可用的工具列表"""
    return [
        file_read,
        file_search,
        code_search,
        list_dir,
        get_viewpoint_pool,
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
    clear_viewpoint_pool_for_tool()
    clear_role_context_for_tool()
