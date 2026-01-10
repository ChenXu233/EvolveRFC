"""共享辩论逻辑

工作流和夜间守护进程共用的多轮辩论机制。
"""

from typing import Optional, Union, TYPE_CHECKING
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


def run_parallel_review(
    content: str,
    current_round: int,
    roles: Optional[list[str]] = None,
) -> list[dict]:
    """并行运行多个角色的评审/辩论

    Args:
        content: 待评审内容（RFC或创新想法）
        current_round: 当前轮次
        roles: 角色列表，默认从配置读取评审者角色

    Returns:
        评审结果列表，每个元素包含: {role, content, vote}
    """
    if roles is None:
        roles = get_reviewer_roles()

    results = []

    for role in roles:
        system_prompt = get_role_prompt(role)
        client = _get_client_for_role(role)

        input_text = f"""请评审以下内容（轮次：{current_round}）：

{content}

请从你的专业角度进行评审，输出格式：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
"""

        try:
            response = client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=input_text),
            ])
            response_text = response.content

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
    """从评审文本中解析投票结果"""
    import re
    # 如果是列表，尝试找到字符串元素
    if isinstance(text, list):
        text = str(text)
    match = re.search(r'立场:\s*(赞成|反对|弃权)', text)
    if match:
        return match.group(1)
    return None


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
