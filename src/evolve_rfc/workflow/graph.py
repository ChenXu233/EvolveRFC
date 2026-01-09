"""LangGraph工作流图定义
"""

from langgraph.graph import StateGraph, END

from .nodes import (
    init_node,
    parallel_review_node,
    vote_analyzer_node,
    human_oversight_node,
    clerk_summary_node,
    timeout_checker_node,
    final_report_node,
)
from .edges import (
    route_after_vote,
    route_after_human,
    route_after_summary,
)


def build_workflow_graph():
    """构建评审工作流图"""
    # 创建状态图
    graph = StateGraph(dict)

    # 添加节点
    graph.add_node("init", init_node)
    graph.add_node("parallel_review", parallel_review_node)
    graph.add_node("vote_analyzer", vote_analyzer_node)
    graph.add_node("human_oversight", human_oversight_node)
    graph.add_node("clerk_summary", clerk_summary_node)
    graph.add_node("timeout_checker", timeout_checker_node)
    graph.add_node("final_report", final_report_node)

    # 设置入口点
    graph.set_entry_point("init")

    # 添加边
    graph.add_edge("init", "parallel_review")
    graph.add_edge("parallel_review", "vote_analyzer")
    graph.add_edge("timeout_checker", "clerk_summary")
    graph.add_edge("clerk_summary", "parallel_review")

    # 条件边 - 投票分析后
    graph.add_conditional_edges(
        "vote_analyzer",
        route_after_vote,
        {
            "human_oversight": "human_oversight",
            "clerk_summary": "clerk_summary",
            "final_report": "final_report",
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
    """构建评审工作流（带配置）"""
    from ..core.router import WorkflowRouter

    # 创建自定义路由器
    router = WorkflowRouter(max_rounds=max_rounds)

    # 创建状态图
    graph = StateGraph(dict)

    # 添加节点
    graph.add_node("init", init_node)
    graph.add_node("parallel_review", parallel_review_node)
    graph.add_node("vote_analyzer", vote_analyzer_node)
    graph.add_node("human_oversight", human_oversight_node)
    graph.add_node("clerk_summary", clerk_summary_node)
    graph.add_node("timeout_checker", timeout_checker_node)
    graph.add_node("final_report", final_report_node)

    # 设置入口点
    graph.set_entry_point("init")

    # 添加边
    graph.add_edge("init", "parallel_review")
    graph.add_edge("parallel_review", "vote_analyzer")
    graph.add_edge("timeout_checker", "clerk_summary")
    graph.add_edge("clerk_summary", "parallel_review")

    # 条件边 - 使用自定义路由器
    def custom_route(state: dict) -> str:
        target = router.route(state)

        route_map = {
            "human_intervention": "human_oversight",
            "round_summary": "clerk_summary",
            "final_report": "final_report",
            "emergency_stop": END,
            "continue": "parallel_review",
        }

        return route_map.get(target.value, END)

    graph.add_conditional_edges(
        "vote_analyzer",
        custom_route,
    )

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
