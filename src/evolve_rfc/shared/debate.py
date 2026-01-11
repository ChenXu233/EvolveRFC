"""共享辩论逻辑

工作流和夜间守护进程共用的多轮辩论机制。
"""

from typing import Optional, Union, TYPE_CHECKING, Callable, Any
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents import get_role_prompt, get_reviewer_roles
from ..settings import get_role_llm_config, BaseLLMConfig

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

    # 获取 token 使用量（通过 last_response）
    # 注意：LangChain 的 stream 不会立即返回 usage，需要用 astream_events 或其他方式
    # 这里我们用近似计算：输入 ≈ system_prompt + input_text，输出 ≈ full_response
    # 对于 OpenAI/Anthropic，可以通过 response.usage 获取准确值

    # 估算输入 token（粗略估计：中文约 1 token/字符，英文约 4 token/词）
    # 实际应使用 tiktoken，但为了简单用字符数/4 估算
    input_text_length = len(system_prompt) + len(input_text)
    input_tokens = input_text_length // 4  # 估算
    output_tokens = len(full_response) // 4  # 估算

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
