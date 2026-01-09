"""工作流边定义
"""

from langgraph.graph import END
from typing import TypedDict

from ..core.router import RouteTarget, default_router
from .nodes import *


def route_after_vote(state: dict) -> str:
    """投票后的路由逻辑"""
    target = default_router.route(state)

    route_map = {
        RouteTarget.HUMAN_INTERVENTION: "human_oversight",
        RouteTarget.ROUND_SUMMARY: "clerk_summary",
        RouteTarget.FINAL_REPORT: "final_report",
        RouteTarget.EMERGENCY_STOP: END,
    }

    return route_map.get(target, END)


def route_after_human(state: dict) -> str:
    """人类介入后的路由逻辑"""
    if state.get("human_decision", {}).get("action") == "终止":
        return END

    if state.get("human_decision", {}).get("action") == "强制通过":
        return "final_report"

    # 继续讨论
    return "parallel_review"


def route_after_summary(state: dict) -> str:
    """书记官汇总后的路由逻辑"""
    target = default_router.route(state)

    if target == RouteTarget.FINAL_REPORT:
        return "final_report"

    return "parallel_review"
