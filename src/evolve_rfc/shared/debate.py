"""共享辩论逻辑

工作流和夜间守护进程共用的多轮辩论机制。
"""

from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..agents import get_role_prompt, RoleType


def run_parallel_review(
    client: ChatOpenAI,
    content: str,
    current_round: int,
    roles: Optional[list[RoleType]] = None,
) -> list[dict]:
    """并行运行多个角色的评审/辩论

 Args:
     client: LLM客户端
     content: 待评审内容（RFC或创新想法）
     current_round: 当前轮次
     roles: 角色列表，默认使用评审者角色

 Returns:
     评审结果列表，每个元素包含: {role, content, vote}
 """
    if roles is None:
        roles = [
            RoleType.ARCHITECT,
            RoleType.SECURITY,
            RoleType.COST_CONTROL,
            RoleType.INNOVATOR,
        ]

    results = []

    for role in roles:
        system_prompt = get_role_prompt(role)

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
            response_text = response.content if hasattr(response, 'content') else str(response)

            # 解析投票结果
            vote = _parse_vote(response_text)

            results.append({
                "role": role.value,
                "content": response_text,
                "vote": vote,
            })

        except Exception as e:
            results.append({
                "role": role.value,
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


def _parse_vote(text: str) -> Optional[str]:
    """从评审文本中解析投票结果"""
    import re
    match = re.search(r'立场:\s*(赞成|反对|弃权)', text)
    if match:
        return match.group(1)
    return None


def check_approval(vote_result: dict, max_rounds: int, current_round: int) -> dict:
    """检查是否通过审核

 Args:
     vote_result: analyze_votes 的返回结果
     max_rounds: 最大轮次
     current_round: 当前轮次

 Returns:
     {approved, finished, reason}
 """
    yes = vote_result["yes"]
    no = vote_result["no"]

    # 规则：
    # - 赞成>=2 且 赞成>反对 = 通过
    # - 反对>=2 = 淘汰
    # - 达到最大轮次 = 结束

    if yes >= 2 and yes > no:
        return {"approved": True, "finished": True, "reason": "通过审核"}
    if no >= 2:
        return {"approved": False, "finished": True, "reason": "反对票过多"}
    if current_round >= max_rounds:
        return {"approved": False, "finished": True, "reason": "达到最大轮次"}

    return {"approved": False, "finished": False, "reason": "继续辩论"}
