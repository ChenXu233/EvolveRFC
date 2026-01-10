"""工作流节点定义
"""

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..settings import get_role_llm_config, BaseLLMConfig
from ..core.state import (
    DiscussionState,
    DiscussionEvent,
    EventType,
    add_event,
)
from ..core.router import default_router
from ..agents import get_role_prompt, get_reviewer_roles
from ..shared import run_parallel_review


# 全局 LLM 客户端缓存
_llm_clients: dict[str, ChatOpenAI | ChatAnthropic] = {}


def _create_llm_client(config: BaseLLMConfig) -> ChatOpenAI | ChatAnthropic:
    """根据配置创建 LLM 客户端"""
    if config.provider == "openai":
        return ChatOpenAI(
            model=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
        )
    elif config.provider == "anthropic":
        return ChatAnthropic(
            model_name=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
            timeout=config.timeout,
            stop=config.stop,
        )
    else:
        raise ValueError(f"不支持的 provider: {config.provider}")


def get_llm_client(role_name: str | None = None) -> ChatOpenAI | ChatAnthropic:
    """获取 LLM 客户端（按角色名称，支持缓存）"""
    key = role_name or "__global__"

    if key not in _llm_clients:
        if role_name:
            config = get_role_llm_config(role_name)
        else:
            config = get_role_llm_config("architect")  # 使用全局配置
        _llm_clients[key] = _create_llm_client(config)

    return _llm_clients[key]


def init_node(state: DiscussionState) -> DiscussionState:
    """初始化节点"""
    return state


def parallel_review_node(state: DiscussionState) -> DiscussionState:
    """并行评审节点 - 多个角色同时评审"""
    rfc_content = state["rfc_content"]
    current_round = state["current_round"]

    # 使用共享的并行评审逻辑
    review_results = run_parallel_review(
        content=rfc_content,
        current_round=current_round,
    )

    # 创建评审事件
    new_events = []
    for result in review_results:
        event = DiscussionEvent(
            event_type=EventType.ROLE_REVIEW,
            actor=result["role"],
            content=result["content"],
            metadata={"round": current_round},
        )
        new_events.append(event)

    # 添加所有事件到状态
    result_state = state
    for event in new_events:
        result_state = add_event(result_state, event)

    return result_state


def vote_analyzer_node(state: DiscussionState) -> DiscussionState:
    """投票统计与分歧分析节点"""
    events = state["events"]
    current_round = state["current_round"]

    # 收集本轮投票
    vote_events = [
        e for e in events
        if e.event_type == EventType.VOTE and e.metadata.get("round") == current_round
    ]

    # 计算投票分布
    if vote_events:
        vote_results = [e.vote_result for e in vote_events if e.vote_result]
        if vote_results:
            yes_votes = vote_results.count("赞成")
            no_votes = vote_results.count("反对")
            abstain_votes = vote_results.count("弃权")

            # 检查是否需要人类介入
            needs_human = default_router.should_human_intervene(state)

            # 添加投票统计事件
            stats_event = DiscussionEvent(
                event_type=EventType.ROUND_COMPLETE,
                actor="system",
                content=f"轮次 {current_round} 投票统计：赞成{yes_votes}，反对{no_votes}，弃权{abstain_votes}",
                metadata={
                    "round": current_round,
                    "vote_summary": {"赞成": yes_votes, "反对": no_votes, "弃权": abstain_votes},
                    "needs_human_intervention": needs_human,
                },
            )
            state = add_event(state, stats_event)

            if needs_human:
                state["awaiting_human_input"] = True
                state["workflow_status"] = "待人类决策"

    return state


def human_oversight_node(state: DiscussionState) -> DiscussionState:
    """人类监督节点 - 工作流暂停，等待人类输入"""
    return state


def clerk_summary_node(state: DiscussionState) -> DiscussionState:
    """书记官总结节点"""
    client = get_llm_client("clerk")
    current_round = state["current_round"]

    # 收集本轮事件
    round_events = [
        e for e in state["events"]
        if e.metadata.get("round") == current_round
    ]

    # 构建总结输入
    input_text = f"""请汇总第 {current_round} 轮讨论结果。

本轮参与讨论的角色发言：
"""

    for event in round_events:
        if event.event_type == EventType.ROLE_REVIEW:
            input_text += f"- {event.actor}: {event.content[:500]}...\n"

    input_text += f"\n当前共识点：{state['consensus_points']}"
    input_text += f"\n待决议项：{state['open_issues']}"

    try:
        response = client.invoke([
            SystemMessage(content=get_role_prompt("clerk")),
            HumanMessage(content=input_text),
        ])
        content = response.content

        # 添加澄清事件
        clarification_event = DiscussionEvent(
            event_type=EventType.CLARIFICATION,
            actor="clerk",
            content=content,
            metadata={"round": current_round},
        )
        state = add_event(state, clarification_event)

        # 更新轮次
        state["current_round"] = current_round + 1

    except Exception as e:
        error_event = DiscussionEvent(
            event_type=EventType.CLARIFICATION,
            actor="clerk",
            content=f"汇总失败：{str(e)}",
            metadata={"round": current_round, "error": True},
        )
        state = add_event(state, error_event)

    return state


def timeout_checker_node(state: DiscussionState) -> DiscussionState:
    """超时检测节点"""
    if state.get("awaiting_human_input", False):
        state["timeout_count"] = state.get("timeout_count", 0) + 1
    return state


def final_report_node(state: DiscussionState) -> DiscussionState:
    """最终报告生成节点"""
    state["workflow_status"] = "已完成"
    return state


def get_all_reviewer_roles() -> list[str]:
    """获取所有评审者角色（从配置动态读取）"""
    return get_reviewer_roles()
