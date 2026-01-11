"""LangGraph工作流图定义
"""

from langgraph.graph import StateGraph, END

from ..core.state import DiscussionState

from .nodes import (
    init_node,
    parallel_review_node,
    vote_analyzer_node,
    viewpoint_pool_manager_node,
    human_oversight_node,
    clerk_summary_node,
    timeout_checker_node,
    final_report_node,
)
from .edges import (
    route_after_human,
)


def build_workflow_graph():
    """构建评审工作流图（集成观点池机制）"""
    # 创建状态图
    graph = StateGraph(DiscussionState)

    # 添加节点
    graph.add_node("init", init_node)
    graph.add_node("parallel_review", parallel_review_node)
    graph.add_node("vote_analyzer", vote_analyzer_node)
    graph.add_node("viewpoint_pool_manager", viewpoint_pool_manager_node)
    graph.add_node("human_oversight", human_oversight_node)
    graph.add_node("clerk_summary", clerk_summary_node)
    graph.add_node("timeout_checker", timeout_checker_node)
    graph.add_node("final_report", final_report_node)

    # 设置入口点
    graph.set_entry_point("init")

    # 添加边
    graph.add_edge("init", "parallel_review")
    graph.add_edge("parallel_review", "vote_analyzer")
    graph.add_edge("viewpoint_pool_manager", "clerk_summary")
    graph.add_edge("timeout_checker", "clerk_summary")
    graph.add_edge("clerk_summary", "parallel_review")

    # 条件边 - 投票分析后（观点池管理）
    def route_after_vote_with_pool(state: DiscussionState) -> str:
        """投票分析后路由，包含观点池检查"""
        # 如果观点池还有活跃观点，继续辩论
        if len(state.get("viewpoint_pool", [])) > 0:
            return "viewpoint_pool_manager"

        # 观点池已空，检查是否需要人类介入
        needs_human = state.get("workflow_status") == "待人类决策"
        if needs_human:
            return "human_oversight"

        return "clerk_summary"

    graph.add_conditional_edges(
        "vote_analyzer",
        route_after_vote_with_pool,
        {
            "viewpoint_pool_manager": "viewpoint_pool_manager",
            "human_oversight": "human_oversight",
            "clerk_summary": "clerk_summary",
            END: END,
        },
    )

    # 条件边 - 观点池管理后
    def route_after_pool_manager(state: DiscussionState) -> str:
        """观点池管理后路由"""
        active_count = len(state.get("viewpoint_pool", []))
        if active_count > 0:
            # 还有未解决的观点，继续辩论
            return "parallel_review"
        else:
            # 所有观点已解决，进入总结
            return "clerk_summary"

    graph.add_conditional_edges(
        "viewpoint_pool_manager",
        route_after_pool_manager,
        {
            "parallel_review": "parallel_review",
            "clerk_summary": "clerk_summary",
            END: END,
        },
    )

    # 条件边 - 人类监督后
    graph.add_conditional_edges(
        "human_oversight",
        route_after_human,
        {
            "final_report": "final_report",
            "parallel_review": "parallel_review",
            END: END,
        },
    )

    return graph.compile()


def build_review_workflow(max_rounds: int = 10):
    """构建评审工作流（带配置，集成观点池机制）"""
    # 创建状态图
    graph = StateGraph(DiscussionState)

    # max_rounds 用于控制最大辩论轮次
    _ = max_rounds  # 保留参数，未来扩展使用

    # 添加节点
    graph.add_node("init", init_node)
    graph.add_node("parallel_review", parallel_review_node)
    graph.add_node("vote_analyzer", vote_analyzer_node)
    graph.add_node("viewpoint_pool_manager", viewpoint_pool_manager_node)
    graph.add_node("human_oversight", human_oversight_node)
    graph.add_node("clerk_summary", clerk_summary_node)
    graph.add_node("timeout_checker", timeout_checker_node)
    graph.add_node("final_report", final_report_node)

    # 设置入口点
    graph.set_entry_point("init")

    # 添加边
    graph.add_edge("init", "parallel_review")
    graph.add_edge("parallel_review", "vote_analyzer")
    graph.add_edge("viewpoint_pool_manager", "clerk_summary")
    graph.add_edge("timeout_checker", "clerk_summary")
    graph.add_edge("clerk_summary", "parallel_review")

    # 条件边 - 投票分析后（观点池管理）
    def route_after_vote_with_pool(state: DiscussionState) -> str:
        """投票分析后路由，包含观点池检查"""
        # 如果观点池还有活跃观点，继续辩论
        if len(state.get("viewpoint_pool", [])) > 0:
            return "viewpoint_pool_manager"

        # 观点池已空，检查是否需要人类介入
        needs_human = state.get("workflow_status") == "待人类决策"
        if needs_human:
            return "human_oversight"

        return "clerk_summary"

    graph.add_conditional_edges(
        "vote_analyzer",
        route_after_vote_with_pool,
        {
            "viewpoint_pool_manager": "viewpoint_pool_manager",
            "human_oversight": "human_oversight",
            "clerk_summary": "clerk_summary",
            END: END,
        },
    )

    # 条件边 - 观点池管理后
    def route_after_pool_manager(state: DiscussionState) -> str:
        """观点池管理后路由"""
        active_count = len(state.get("viewpoint_pool", []))
        if active_count > 0:
            # 还有未解决的观点，继续辩论
            return "parallel_review"
        else:
            # 所有观点已解决，进入总结
            return "clerk_summary"

    graph.add_conditional_edges(
        "viewpoint_pool_manager",
        route_after_pool_manager,
        {
            "parallel_review": "parallel_review",
            "clerk_summary": "clerk_summary",
            END: END,
        },
    )

    # 条件边 - 人类监督后
    graph.add_conditional_edges(
        "human_oversight",
        lambda s: "final_report" if s.get("human_decision", {}).get("action") == "终止" else "parallel_review",
        {
            "final_report": "final_report",
            "parallel_review": "parallel_review",
            END: END,
        },
    )

    return graph.compile()
