"""共享辩论逻辑

工作流和夜间守护进程共用的多轮辩论机制。
"""

from typing import Optional, Union, TYPE_CHECKING, Callable, Any, List
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents import get_role_prompt, get_reviewer_roles
from ..settings import get_role_llm_config, BaseLLMConfig
from ..core.state import Viewpoint, ViewpointStatus

# 导入工具（用于多段思考）
from .tools import get_all_tools

if TYPE_CHECKING:
    pass


def _create_llm_client(
    role_name: str, config: BaseLLMConfig
) -> ChatOpenAI | ChatAnthropic:
    """根据配置创建 LLM 客户端"""

    if not config.api_key:
        raise ValueError(f"角色 {role_name} 的 LLM 配置缺少 API 密钥")

    if config.provider == "openai":
        return ChatOpenAI(
            model=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
            api_key=config.api_key,
        )
    elif config.provider == "anthropic":
        return ChatAnthropic(
            model_name=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
            timeout=config.timeout,
            stop=config.stop,
            api_key=config.api_key,
        )
    else:
        raise ValueError(f"不支持的 provider: {config.provider}")


def _get_client_for_role(role: str) -> ChatOpenAI | ChatAnthropic:
    """获取角色对应的 LLM 客户端"""
    config = get_role_llm_config(role)
    return _create_llm_client(role, config)


def _format_chunk_content(chunk: Any) -> str:
    """格式化 chunk content 为字符串"""
    content = chunk.content
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # 处理列表类型的 content（如 image_url 等）
        return str(content)
    else:
        return str(content)


def _get_token_usage(
    client: ChatOpenAI | ChatAnthropic,
    system_prompt: str,
    input_text: str,
    full_response: str,
) -> tuple[int, int]:
    """获取真实的 token 使用量
    
    对于流式调用，LangChain 不会立即返回 usage。
    我们通过 invoke 方式获取准确值（用于 OpenAI/Anthropic）。
    """
    # 方法1：尝试通过 invoke 获取 usage（最准确）
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=input_text),
    ]
    
    try:
        # 使用非流式调用获取准确的 usage
        response = client.invoke(messages)
        # 使用 getattr 安全获取 usage（避免类型检查错误）
        usage = getattr(response, 'usage', None)
        if usage:
            prompt_tokens = getattr(usage, 'prompt_tokens', None) or getattr(usage, 'input_tokens', None)
            completion_tokens = getattr(usage, 'completion_tokens', None) or getattr(usage, 'output_tokens', None)
            if prompt_tokens is not None and completion_tokens is not None:
                return prompt_tokens, completion_tokens
    except Exception:
        pass
    
    # 回退到估算
    input_text_length = len(system_prompt) + len(input_text)
    input_tokens = input_text_length // 4
    output_tokens = len(full_response) // 4
    
    return input_tokens, output_tokens


def _run_role_review_stream(
    role: str,
    content: str,
    current_round: int,
    stream_callback: Optional[Callable[[str], None]] = None,
    previous_results: Optional[list[dict]] = None,
    token_callback: Optional[Callable[[dict], None]] = None,
) -> str:
    """流式运行单个角色的评审

    Args:
        role: 角色名称
        content: 待评审内容
        current_round: 当前轮次
        stream_callback: 流式回调函数，接收内容片段
        previous_results: 之前角色的评审结果，用于辩论参考
        token_callback: Token使用量回调，接收 {input_tokens, output_tokens, total_tokens, remaining}

    Returns:
        完整的评审内容
    """
    import re

    system_prompt = get_role_prompt(role)
    client = _get_client_for_role(role)

    # 获取模型上下文窗口大小（默认 128K）
    config = get_role_llm_config(role)
    model_max_tokens = getattr(config, 'max_tokens', 128000) or 128000

    # 构建输入文本
    input_text = f"请评审以下内容（轮次：{current_round}）：\n\n{content}\n"

    # 如果有之前的评审结果，添加辩论历史
    if previous_results:
        input_text += "\n=== 之前角色的观点 ===\n"
        for result in previous_results:
            role_name = result.get("role", "未知")
            role_content = result.get("content", "")
            role_vote = result.get("vote", "")

            # 提取论点列表
            points = []
            point_pattern = r"论点\d+[:：]([^\n]+)"
            for match in re.finditer(point_pattern, role_content):
                points.append(match.group(1).strip())

            input_text += f"\n【{role_name}】立场: {role_vote or '未知'}\n"
            if points:
                for i, p in enumerate(points[:3], 1):  # 只取前3个论点
                    input_text += f"  论点{i}: {p[:100]}...\n"
            else:
                input_text += f"  观点: {role_content[:200]}...\n"

        input_text += "\n=== 你的任务 ===\n请参考以上观点进行辩论：\n1. 如果同意某个论点，补充新的论据\n2. 如果反对某个论点，说明理由并提出替代方案\n3. 如果有新的关注点，独立提出新论点\n"

    input_text += '\n请从你的专业角度进行评审，输出格式（必须严格遵循）：\n\n## 肯定点\n- [如果有值得肯定的设计，写在这里]\n\n## 论点列表\n论点1: "<一句话核心观点>"\n论据: ["<支撑论据1>", "<支撑论据2>"]\n立场: "赞成|反对|弃权"\n置信度: 0.0-1.0\n\n论点2: "<一句话核心观点>" (可选)\n论据: ["<支撑论据1>", "<支撑论据2>"]\n立场: "赞成|反对|弃权"\n置信度: 0.0-1.0\n'

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=input_text),
    ]

    # 收集完整响应
    full_response = ""
    input_tokens = 0
    output_tokens = 0

    # 流式调用
    for chunk in client.stream(messages):
        chunk_text = _format_chunk_content(chunk)
        if chunk_text:
            full_response += chunk_text
            # 调用回调函数传递片段
            if stream_callback:
                stream_callback(chunk_text)

    # 获取真实的 token 使用量
    input_tokens, output_tokens = _get_token_usage(
        client, system_prompt, input_text, full_response
    )

    total_tokens = input_tokens + output_tokens
    remaining = max(0, model_max_tokens - total_tokens)

    # 触发 token 回调
    if token_callback:
        token_callback({
            "role": role,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "remaining": remaining,
            "max_tokens": model_max_tokens,
            "usage_percent": (total_tokens / model_max_tokens * 100) if model_max_tokens > 0 else 0,
        })

    return full_response


def run_debate(
    content: str,
    current_round: int,
    roles: Optional[list[str]] = None,
    stream_callback: Optional[Callable[[str, str], None]] = None,
    token_callback: Optional[Callable[[dict], None]] = None,
) -> list[dict]:
    """顺序辩论模式 - 每个角色依次发言，能看到之前所有角色的观点

    Args:
        content: 待评审内容（RFC或创新想法）
        current_round: 当前轮次
        roles: 角色列表，默认从配置读取评审者角色
        stream_callback: 可选的流式回调，参数为 (role, chunk_content)
        token_callback: 可选的token使用量回调，接收 {role, input_tokens, output_tokens, total_tokens, remaining, max_tokens, usage_percent}

    Returns:
        评审结果列表，每个元素包含: {role, content, vote}
    """
    if roles is None:
        roles = get_reviewer_roles()

    results = []

    for role in roles:
        # 创建流式回调包装器
        def make_callback(rl: str) -> Callable[[str], None]:
            def callback(chunk: str) -> None:
                if stream_callback:
                    stream_callback(rl, chunk)

            return callback

        role_callback = make_callback(role)

        # 创建 token 回调包装器
        def make_token_callback(rl: str) -> Callable[[dict], None]:
            def callback(token_data: dict) -> None:
                token_data["role"] = rl
                if token_callback:
                    token_callback(token_data)

            return callback

        role_token_callback = make_token_callback(role)

        try:
            # 传入之前的结果，让当前角色可以看到辩论历史
            response_text = _run_role_review_stream(
                role=role,
                content=content,
                current_round=current_round,
                stream_callback=role_callback,
                previous_results=results,  # 传递历史结果
                token_callback=role_token_callback,
            )

            # 解析投票结果
            vote = _parse_vote(response_text)

            results.append({
                "role": role,
                "content": response_text,
                "vote": vote,
            })

        except Exception as e:
            results.append({
                "role": role,
                "content": f"评审失败：{str(e)}",
                "vote": None,
            })

    return results


# 保持向后兼容的别名
run_parallel_review = run_debate


def analyze_votes(results: list[dict]) -> dict:
    """分析投票结果

    Args:
        results: run_parallel_review 的返回结果

    Returns:
        投票统计: {yes, no, abstain, needs_human}
    """
    votes = [r["vote"] for r in results if r["vote"]]
    if not votes:
        return {"yes": 0, "no": 0, "abstain": 0, "needs_human": False}

    yes_count = votes.count("赞成")
    no_count = votes.count("反对")
    abstain_count = votes.count("弃权")

    # 反对票超过30%视为需要人类介入
    total = len(votes)
    needs_human = (no_count / total) > 0.3

    return {
        "yes": yes_count,
        "no": no_count,
        "abstain": abstain_count,
        "needs_human": needs_human,
    }


def _parse_vote(text: Union[str, list]) -> Optional[str]:
    """从评审文本中解析投票结果

    支持两种格式：
    1. 旧格式: 立场: "赞成|反对|弃权"
    2. 新格式: 论点列表中每个论点都有自己的立场

    返回值：如果有多个论点，返回多数立场；如果无法解析，返回None
    """
    import re
    # 如果是列表，尝试找到字符串元素
    if isinstance(text, list):
        text = str(text)

    # 查找所有论点中的立场
    all_votes = []

    # 匹配论点1、论点2等格式中的立场
    vote_patterns = [
        r"论点\d+[:：].*?立场[:：]\s*[\"']?\s*(赞成|反对|弃权)",
        r"立场[:：]\s*[\"']?\s*(赞成|反对|弃权)",
        r"(赞成|反对|弃权)[,，]",
    ]

    for pattern in vote_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            vote = match.strip()
            # 标准化
            if vote in ["同意", "赞成", "支持"]:
                all_votes.append("赞成")
            elif vote in ["反对", "不支持", "拒绝"]:
                all_votes.append("反对")
            elif vote in ["弃权", "不发表意见"]:
                all_votes.append("弃权")

    if not all_votes:
        return None

    # 返回多数立场
    from collections import Counter

    vote_counts = Counter(all_votes)
    return vote_counts.most_common(1)[0][0]


def check_approval(
    vote_result: dict,
    max_rounds: int,
    current_round: int,
    yes_votes_needed: int = 2,
    no_votes_limit: int = 2,
    require_yes_over_no: bool = True,
) -> dict:
    """检查是否通过审核

    Args:
        vote_result: analyze_votes 的返回结果
        max_rounds: 最大轮次
        current_round: 当前轮次
        yes_votes_needed: 需要的最少赞成票
        no_votes_limit: 反对票上限
        require_yes_over_no: 是否要求赞成票多于反对票

    Returns:
        {approved, finished, reason}
    """
    yes = vote_result["yes"]
    no = vote_result["no"]

    # 检查赞成票是否足够
    if yes >= yes_votes_needed:
        if require_yes_over_no:
            if yes > no:
                return {"approved": True, "finished": True, "reason": "通过审核"}
        else:
            return {"approved": True, "finished": True, "reason": "通过审核"}

    # 检查反对票是否超过上限
    if no >= no_votes_limit:
        return {"approved": False, "finished": True, "reason": "反对票过多"}

    # 检查是否达到最大轮次
    if current_round >= max_rounds:
        return {"approved": False, "finished": True, "reason": "达到最大轮次"}

    return {"approved": False, "finished": False, "reason": "继续辩论"}


# === 观点池相关函数 ===

def _normalize_stance(stance: str) -> str:
    """标准化立场表达"""
    stance = stance.strip()
    if stance in ["同意", "赞成", "支持", "yes", "Yes", "YES"]:
        return "赞成"
    elif stance in ["反对", "不支持", "拒绝", "no", "No", "NO"]:
        return "反对"
    elif stance in ["弃权", "不发表意见", "中立", "abstain", "Abstain"]:
        return "弃权"
    return stance


def parse_viewpoints(text: str) -> List[dict]:
    """从评审文本中解析论点（支持多种格式）

    Args:
        text: 评审文本内容

    Returns:
        论点列表，每个元素包含 {content, evidence, stance, is_new}
    """
    import re

    viewpoints = []

    # 辅助函数：检查内容是否已存在
    def content_exists(content: str) -> bool:
        return any(vp["content"] == content for vp in viewpoints)

    # 模式1：明确标注为"新观点"的论点
    # 格式：论点1（新观点）: "..." 论据: [...] 立场: ...
    new_pattern = r"论点\s*\d+\s*[\（\(]?\s*新\s*观点\s*[\）\)]?[:：]\s*[\"']([^\"']+)[\"']\s*\n论据:\s*\[([^\]]+)\]\s*\n立场:\s*[\"']?([^\"'\n]+)[\"']?"

    for match in re.finditer(new_pattern, text, re.DOTALL):
        content = match.group(1).strip()
        evidence_str = match.group(2)
        stance = match.group(3).strip()

        if content_exists(content):
            continue

        evidence = [e.strip().strip('"').strip("'") for e in evidence_str.split(',')]

        viewpoints.append({
            "content": content,
            "evidence": evidence,
            "stance": _normalize_stance(stance),
            "is_new": True,
        })

    # 模式2：论点列表格式（通用格式）
    # 格式：论点1: "..." 论据: [...] 立场: ...
    general_pattern = r"论点\s*\d+[:：]\s*[\"']([^\"']+)[\"']\s*\n?\s*论据:\s*\[([^\]]+)\]\s*\n?\s*立场:\s*[\"']?([^\"'\n]+)[\"']?"

    for match in re.finditer(general_pattern, text, re.DOTALL | re.IGNORECASE):
        content = match.group(1).strip()
        evidence_str = match.group(2)
        stance = match.group(3).strip()

        if content_exists(content):
            continue

        evidence = [e.strip().strip('"').strip("'") for e in evidence_str.split(',')]

        viewpoints.append({
            "content": content,
            "evidence": evidence,
            "stance": _normalize_stance(stance),
            "is_new": False,
        })

    # 模式3：简化格式（论点: 内容，论据: [...]，立场: ...）
    simple_pattern = r"论点[:：]\s*([^\n]+)\n?\s*论据[:：]\s*\[([^\]]+)\]\s*\n?\s*立场[:：]\s*([^\n]+)"

    for match in re.finditer(simple_pattern, text, re.DOTALL | re.IGNORECASE):
        content = match.group(1).strip()
        evidence_str = match.group(2)
        stance = match.group(3).strip()

        if content_exists(content):
            continue

        evidence = [e.strip().strip('"').strip("'") for e in evidence_str.split(',')]

        viewpoints.append({
            "content": content,
            "evidence": evidence,
            "stance": _normalize_stance(stance),
            "is_new": False,
        })

    return viewpoints


def build_viewpoint_pool_context(viewpoint_pool: List[Viewpoint]) -> str:
    """构建观点池上下文字符串

    Args:
        viewpoint_pool: 当前观点池

    Returns:
        用于 LLM 提示的上下文字符串
    """
    if not viewpoint_pool:
        return "当前观点池为空，可以提出新的核心观点。"

    context_lines = ["=== 当前活跃观点池（最多3个，必须逐一回应）==="]

    for i, vp in enumerate(viewpoint_pool, 1):
        status_icon = "🔴" if vp.status == ViewpointStatus.ACTIVE else "🟢"
        votes_info = f"👍{vp.vote_count.get('赞成', 0)} 👎{vp.vote_count.get('反对', 0)}"

        context_lines.append(f"\n{status_icon} 观点{i} [{vp.id}]: {vp.content}")
        context_lines.append(f"   提出者: {vp.proposer} | 投票: {votes_info}")
        context_lines.append(f"   论据: {'; '.join(vp.evidence[:2])}")

    context_lines.append("\n=== 讨论规则 ===")
    context_lines.append("1. 你必须先回应观点池中的所有观点（每个观点至少一条意见）")
    context_lines.append("2. 只能提出最多1个新观点（如果观点池未满）")
    context_lines.append("3. 回应现有观点时，说明支持、反对或补充理由")

    return "\n".join(context_lines)


def can_propose_new_viewpoint(viewpoint_pool: List[Viewpoint], pool_limit: int = 3) -> bool:
    """检查是否还能提出新观点"""
    return len(viewpoint_pool) < pool_limit


def run_review_with_viewpoint_pool(
    role: str,
    content: str,
    current_round: int,
    viewpoint_pool: List[Viewpoint],
    stream_callback: Optional[Callable[[str], None]] = None,
    previous_results: Optional[list[dict]] = None,
    token_callback: Optional[Callable[[dict], None]] = None,
) -> dict:
    """带观点池上下文的角色评审

    Args:
        role: 角色名称
        content: 待评审内容
        current_round: 当前轮次
        viewpoint_pool: 当前观点池
        stream_callback: 流式回调函数
        previous_results: 之前角色的评审结果
        token_callback: Token使用量回调

    Returns:
        评审结果 {role, content, vote, new_viewpoints}
    """
    import re

    system_prompt = get_role_prompt(role)
    client = _get_client_for_role(role)

    config = get_role_llm_config(role)
    model_max_tokens = getattr(config, 'max_tokens', 128000) or 128000

    # 构建输入文本
    input_text = f"请评审以下内容（轮次：{current_round}）：\n\n{content}\n"

    # 添加观点池上下文
    input_text += "\n" + build_viewpoint_pool_context(viewpoint_pool)

    # 如果有之前的评审结果，添加辩论历史
    if previous_results:
        input_text += "\n=== 之前角色的观点 ===\n"
        for result in previous_results:
            role_name = result.get("role", "未知")
            role_content = result.get("content", "")
            role_vote = result.get("vote", "")

            # 提取论点列表
            points = []
            point_pattern = r"论点\d+[:：]([^\n]+)"
            for match in re.finditer(point_pattern, role_content):
                points.append(match.group(1).strip())

            input_text += f"\n【{role_name}】立场: {role_vote or '未知'}\n"
            if points:
                for i, p in enumerate(points[:3], 1):
                    input_text += f"  论点{i}: {p[:100]}...\n"
            else:
                input_text += f"  观点: {role_content[:200]}...\n"

    # 检查是否可以提出新观点
    can_add = can_propose_new_viewpoint(viewpoint_pool)

    input_text += '''
=== 输出格式（必须严格遵循） ===

## 肯定点
- [如果有值得肯定的设计，写在这里]

## 新观点（只有明确同意/反对现有观点后，才能提出新观点）
论点1（新观点）: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
立场: "赞成|反对|弃权"

## 对现有观点的回应
回应1: "针对观点X的ID，你的看法"
立场: "赞成|反对|弃权"
'''

    if not can_add:
        input_text += '''
（注意：观点池已满，不能提出新观点，只能回应现有观点）
'''

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=input_text),
    ]

    # 收集完整响应
    full_response = ""
    input_tokens = 0
    output_tokens = 0

    # 流式调用
    for chunk in client.stream(messages):
        chunk_text = _format_chunk_content(chunk)
        if chunk_text:
            full_response += chunk_text
            if stream_callback:
                stream_callback(chunk_text)

    # 获取真实的 token 使用量
    input_tokens, output_tokens = _get_token_usage(
        client, system_prompt, input_text, full_response
    )

    total_tokens = input_tokens + output_tokens
    remaining = max(0, model_max_tokens - total_tokens)

    if token_callback:
        token_callback({
            "role": role,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "remaining": remaining,
            "max_tokens": model_max_tokens,
            "usage_percent": (total_tokens / model_max_tokens * 100) if model_max_tokens > 0 else 0,
        })

    # 解析投票结果
    vote = _parse_vote(full_response)

    # 解析新观点
    new_viewpoints = parse_viewpoints(full_response)

    return {
        "role": role,
        "content": full_response,
        "vote": vote,
        "new_viewpoints": new_viewpoints,
    }


# === 多段思考 Agent（ReAct 模式）===

def run_review_with_tools(
    role: str,
    content: str,
    current_round: int,
    viewpoint_pool: List[Viewpoint],
    stream_callback: Optional[Callable[[str], None]] = None,
    previous_results: Optional[list[dict]] = None,
    token_callback: Optional[Callable[[dict], None]] = None,
    max_iterations: int = 10,
) -> dict:
    """带工具调用的多段思考评审（ReAct 模式）

    实现真正的 AI 思考过程：
    1. 思考：分析问题，决定是否需要调用工具
    2. 行动：调用工具获取信息（搜索代码、读取文件等）
    3. 观察：获取工具返回结果
    4. 重复：直到得到最终答案

    Args:
        role: 角色名称
        content: 待评审内容
        current_round: 当前轮次
        viewpoint_pool: 当前观点池
        stream_callback: 流式回调函数
        previous_results: 之前角色的评审结果
        token_callback: Token使用量回调
        max_iterations: 最大迭代次数（防止无限循环）

    Returns:
        评审结果 {role, content, vote, new_viewpoints, tool_calls}
    """
    try:
        from langgraph.prebuilt import create_react_agent
        from langchain_core.messages import HumanMessage
    except ImportError:
        # 如果 langgraph.prebuilt 不可用，回退到普通模式
        return run_review_with_viewpoint_pool(
            role=role,
            content=content,
            current_round=current_round,
            viewpoint_pool=viewpoint_pool,
            stream_callback=stream_callback,
            previous_results=previous_results,
            token_callback=token_callback,
        )

    system_prompt = get_role_prompt(role)
    client = _get_client_for_role(role)

    config = get_role_llm_config(role)
    model_max_tokens = getattr(config, 'max_tokens', 128000) or 128000

    # 构建输入文本
    input_text = f"请评审以下内容（轮次：{current_round}）：\n\n{content}\n"

    # 添加观点池上下文
    input_text += "\n" + build_viewpoint_pool_context(viewpoint_pool)

    # 如果有之前的评审结果，添加辩论历史
    if previous_results:
        import re
        input_text += "\n=== 之前角色的观点 ===\n"
        for result in previous_results:
            role_name = result.get("role", "未知")
            role_content = result.get("content", "")
            role_vote = result.get("vote", "")

            points = []
            point_pattern = r"论点\d+[:：]([^\n]+)"
            for match in re.finditer(point_pattern, role_content):
                points.append(match.group(1).strip())

            input_text += f"\n【{role_name}】立场: {role_vote or '未知'}\n"
            if points:
                for i, p in enumerate(points[:3], 1):
                    input_text += f"  论点{i}: {p[:100]}...\n"
            else:
                input_text += f"  观点: {role_content[:200]}...\n"

    # 添加工具使用说明
    input_text += """
=== 可用工具 ===
你可以调用以下工具来获取信息或管理观点：

【信息获取工具】
- file_read: 读取文件内容。参数: file_path(文件路径)
- file_search: 递归查找文件。参数: start_dir(起始目录), pattern(文件匹配模式, 如 "*.py")
- code_search: 在代码中搜索正则表达式。参数: pattern(正则表达式), file_pattern(文件匹配模式)
- list_dir: 列出目录内容。参数: dir_path(目录路径)

【观点管理工具】（非常重要，必须使用）
- propose_viewpoint: 提出新观点到观点池。
  参数:
    - content: 观点内容（一句话概括核心问题）
    - evidence: 支撑论据列表（JSON数组格式，如 ["论据1", "论据2"]）
    - stance: 你的立场（必须是 "赞成"、"反对" 或 "弃权" 之一）
  示例: propose_viewpoint({"content": "API设计过于复杂", "evidence": ["接口参数过多", "缺乏默认值"], "stance": "反对"})

- respond_to_viewpoint: 回应观点池中的已有观点。
  参数:
    - viewpoint_id: 要回应的观点ID
    - response: 你的回应内容
    - stance: 你对该观点的立场（"赞成"、"反对" 或 "弃权"）
  示例: respond_to_viewpoint({"viewpoint_id": "VP-001", "response": "同意此观点，补充如下...", "stance": "赞成"})

=== 核心规则（必须遵守） ===
【重要】如果你发现了新的设计问题或关注点，必须通过调用 propose_viewpoint 工具来添加观点，而不是在回复文本中提及！
【重要】如果你想对现有观点表达立场，必须调用 respond_to_viewpoint 工具！
【重要】只有在观点池已满（已有3个活跃观点）时，才不能提出新观点！

=== 思考流程 ===
1. 先思考是否需要调用工具获取更多信息
2. 如果需要，调用相关工具
3. 如果观点池未满且发现新问题，调用 propose_viewpoint 提出新观点（这是唯一添加观点的方式！）
4. 对观点池中的现有观点，调用 respond_to_viewpoint 表达你的立场
5. 根据工具返回的结果继续思考
6. 最终给出评审结论

=== 输出格式 ===
## 肯定点
- [如果有值得肯定的设计]

## 总结
[对你的整体评审结果]
"""

    # 获取工具列表
    tools = get_all_tools()

    # 创建 ReAct Agent
    try:
        # LangGraph 新版本使用 prompt 参数（旧版本是 state_modifier）
        agent = create_react_agent(client, tools, prompt=system_prompt)
    except Exception as e:
        # 如果创建失败，回退到普通模式
        if stream_callback:
            stream_callback(f"\n[回退到普通模式: {str(e)[:100]}]\n")
        return run_review_with_viewpoint_pool(
            role=role,
            content=content,
            current_round=current_round,
            viewpoint_pool=viewpoint_pool,
            stream_callback=stream_callback,
            previous_results=previous_results,
            token_callback=token_callback,
        )

    # 收集完整响应
    full_response = ""
    tool_calls = []
    input_tokens = 0
    output_tokens = 0
    thought_cycle_count = 0  # 记录实际思考轮次（每次AI决定调用工具算一轮）
    max_thought_cycles = min(max_iterations, 15)  # 最多15轮思考，使用传入的max_iterations
    force_stop = False  # 强制停止标志

    try:
        # 运行 Agent（支持工具调用）
        for event in agent.stream(
            {"messages": [HumanMessage(content=input_text)]},
            {"recursion_limit": max_thought_cycles * 3},  # 每个思考轮次可能产生多个事件
        ):
            if force_stop:
                break

            try:
                # 处理事件，提取消息内容
                if "messages" in event:
                    for message in event["messages"]:
                        # 检测 AI 是否开始新的一轮思考（决定调用工具）
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            thought_cycle_count += 1

                            # 防止无限循环安全检查
                            if thought_cycle_count > max_thought_cycles:
                                if stream_callback:
                                    stream_callback(f"\n[警告: 达到最大思考轮次 {max_thought_cycles}，强制结束]\n")
                                force_stop = True
                                break

                        # AI 的思考和回复
                        if hasattr(message, 'content') and message.content:
                            content_str = str(message.content)
                            # 过滤掉纯工具调用定义，保留思考内容和最终回复
                            # 只过滤以 JSON 格式的工具调用块
                            lines = content_str.split('\n')
                            filtered_lines = []
                            skip_next = False
                            for i, line in enumerate(lines):
                                if skip_next:
                                    skip_next = False
                                    continue
                                # 跳过纯 JSON 工具调用块
                                if line.strip().startswith('"name":') or line.strip().startswith('"args"'):
                                    # 检查是否是工具调用定义的一部分
                                    if i > 0 and ('tool_calls' in lines[i-1] or 'function' in lines[i-1].lower()):
                                        skip_next = True
                                        continue
                                filtered_lines.append(line)

                            clean_content = '\n'.join(filtered_lines).strip()
                            if clean_content:
                                full_response += clean_content + "\n"
                                if stream_callback:
                                    stream_callback(clean_content)

                        # 工具调用记录
                        if hasattr(message, 'tool_calls') and message.tool_calls:
                            for tc in message.tool_calls:
                                tool_calls.append({
                                    "tool": tc.get("name", "unknown"),
                                    "arguments": tc.get("args", {}),
                                })

                # 处理工具结果（带错误恢复）
                if "tool" in event:
                    tool_result = event["tool"]
                    try:
                        if hasattr(tool_result, 'content'):
                            result_content = str(tool_result.content)
                            # 将工具结果添加到响应中
                            if result_content and result_content.strip():
                                tool_result_text = f"\n[工具结果: {result_content[:200]}]\n"
                                full_response += tool_result_text
                                if stream_callback:
                                    stream_callback(tool_result_text)
                            if tool_calls:
                                tool_calls[-1]["result"] = result_content[:500] if result_content else ""
                    except Exception as tool_err:
                        # 单个工具调用失败不影响整体
                        error_text = f"\n[工具执行错误: {str(tool_err)[:100]}]\n"
                        full_response += error_text
                        if stream_callback:
                            stream_callback(error_text)
                        if tool_calls:
                            tool_calls[-1]["result"] = f"错误: {str(tool_err)[:200]}"

            except Exception as event_err:
                # 单个事件处理失败，继续处理下一个
                error_text = f"\n[事件处理错误: {str(event_err)[:100]}]\n"
                full_response += error_text
                if stream_callback:
                    stream_callback(error_text)
                continue

        # 获取真实的 token 使用量
        input_tokens, output_tokens = _get_token_usage(
            client, system_prompt, input_text, full_response
        )

        total_tokens = input_tokens + output_tokens
        remaining = max(0, model_max_tokens - total_tokens)

        if token_callback:
            token_callback({
                "role": role,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "remaining": remaining,
                "max_tokens": model_max_tokens,
                "usage_percent": (total_tokens / model_max_tokens * 100) if model_max_tokens > 0 else 0,
            })

    except Exception as outer_err:
        # 外部异常处理：保留已收集的响应，而不是完全回退
        error_msg = f"\n[评审过程出错: {str(outer_err)[:100]}]\n"
        full_response += error_msg
        if stream_callback:
            stream_callback(error_msg)

        # 获取真实的 token 使用量（即使出错也要更新）
        input_tokens, output_tokens = _get_token_usage(
            client, system_prompt, input_text, full_response
        )
        total_tokens = input_tokens + output_tokens
        remaining = max(0, model_max_tokens - total_tokens)

        if token_callback:
            token_callback({
                "role": role,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "remaining": remaining,
                "max_tokens": model_max_tokens,
                "usage_percent": (total_tokens / model_max_tokens * 100) if model_max_tokens > 0 else 0,
            })

    # 解析投票结果
    vote = _parse_vote(full_response)

    # 解析新观点
    new_viewpoints = parse_viewpoints(full_response)

    # 从工具调用中提取通过 propose_viewpoint 添加的观点
    from .tools import get_viewpoints_from_tool
    tool_viewpoints = get_viewpoints_from_tool()
    for vp in tool_viewpoints:
        # 避免重复添加
        if not any(v["content"] == vp["content"] for v in new_viewpoints):
            new_viewpoints.append({
                "content": vp.get("content", ""),
                "evidence": vp.get("evidence", []),
                "stance": _normalize_stance(vp.get("stance", "弃权")),
                "is_new": True,
            })

    return {
        "role": role,
        "content": full_response,
        "vote": vote,
        "new_viewpoints": new_viewpoints,
        "tool_calls": tool_calls,  # 记录工具调用历史
    }
