"""工作流路由器 - 集中管理路由逻辑

将路由逻辑从节点中分离，便于维护和配置。
"""

from enum import Enum
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import DiscussionState


class RouteTarget(Enum):
    """路由目标枚举"""
    CONTINUE = "continue"                 # 继续讨论
    HUMAN_INTERVENTION = "human"          # 人类监督节点
    ROUND_SUMMARY = "summary"             # 书记官汇总
    FINAL_REPORT = "final_report"         # 生成最终报告
    EMERGENCY_STOP = "stop"               # 紧急停止


@dataclass
class RoutingRule:
    """路由规则定义"""
    name: str
    condition: Callable[["DiscussionState"], bool]
    priority: int
    target: RouteTarget


class WorkflowRouter:
    """工作流路由器 - 集中管理路由逻辑"""

    def __init__(
        self,
        max_rounds: int = 10,
        deadlock_opposition_ratio: float = 0.3,
        consensus_quorum: float = 0.8,
    ):
        self.max_rounds = max_rounds
        self.deadlock_opposition_ratio = deadlock_opposition_ratio
        self.consensus_quorum = consensus_quorum
        self.rules = self._build_rules()

    def _build_rules(self) -> list[RoutingRule]:
        """构建路由规则列表（按优先级排序）"""
        return [
            RoutingRule(
                name="emergency_stop",
                condition=lambda s: s.get("human_decision", {}).get("action") == "终止",
                priority=1,
                target=RouteTarget.EMERGENCY_STOP,
            ),
            RoutingRule(
                name="human_intervention",
                condition=lambda s: s.get("awaiting_human_input", False),
                priority=2,
                target=RouteTarget.HUMAN_INTERVENTION,
            ),
            RoutingRule(
                name="max_rounds_reached",
                condition=lambda s: s.get("current_round", 0) >= self.max_rounds,
                priority=3,
                target=RouteTarget.FINAL_REPORT,
            ),
            RoutingRule(
                name="consensus_reached",
                condition=lambda s: len(s.get("open_issues", [])) == 0,
                priority=4,
                target=RouteTarget.FINAL_REPORT,
            ),
            RoutingRule(
                name="round_complete",
                condition=lambda s: True,  # 默认每轮结束后汇总
                priority=5,
                target=RouteTarget.ROUND_SUMMARY,
            ),
        ]

    def route(self, state: "DiscussionState") -> RouteTarget:
        """根据状态路由到下一个节点"""
        sorted_rules = sorted(self.rules, key=lambda r: r.priority)
        for rule in sorted_rules:
            if rule.condition(state):
                return rule.target
        return RouteTarget.CONTINUE

    def should_human_intervene(self, state: "DiscussionState") -> bool:
        """判断是否需要人类介入"""
        # 检查是否有重大分歧（反对票 > 30%）
        events = state.get("events", [])
        votes = [e for e in events if e.event_type.value == "vote"]

        if not votes:
            return False

        vote_results = [e.vote_result for e in votes if e.vote_result]
        if not vote_results:
            return False

        opposition_count = vote_results.count("反对")
        total_votes = len(vote_results)

        return (opposition_count / total_votes) > self.deadlock_opposition_ratio


# 全局路由器实例
default_router = WorkflowRouter()
