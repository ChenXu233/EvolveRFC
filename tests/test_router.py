"""路由器单元测试
"""

import pytest
from datetime import datetime

from evolve_rfc.core.state import (
    DiscussionEvent,
    DiscussionState,
    EventType,
)
from evolve_rfc.core.router import (
    WorkflowRouter,
    RouteTarget,
    RoutingRule,
)


class TestWorkflowRouter:
    """WorkflowRouter 测试类"""

    def test_router_initialization(self):
        """测试路由器初始化"""
        router = WorkflowRouter(max_rounds=5)
        assert router.max_rounds == 5
        assert len(router.rules) == 5

    def test_emergency_stop_route(self):
        """测试紧急停止路由"""
        router = WorkflowRouter()
        state = {
            "human_decision": {"action": "终止"},
            "current_round": 1,
            "open_issues": ["issue-1"],
        }

        result = router.route(state)
        assert result == RouteTarget.EMERGENCY_STOP

    def test_human_intervention_route(self):
        """测试人类介入路由"""
        router = WorkflowRouter()
        state = {
            "awaiting_human_input": True,
            "current_round": 1,
            "open_issues": ["issue-1"],
        }

        result = router.route(state)
        assert result == RouteTarget.HUMAN_INTERVENTION

    def test_max_rounds_route(self):
        """测试最大轮次路由"""
        router = WorkflowRouter(max_rounds=5)
        state = {
            "current_round": 5,
            "open_issues": ["issue-1"],
        }

        result = router.route(state)
        assert result == RouteTarget.FINAL_REPORT

    def test_consensus_route(self):
        """测试达成共识路由"""
        router = WorkflowRouter()
        state = {
            "current_round": 1,
            "open_issues": [],
        }

        result = router.route(state)
        assert result == RouteTarget.FINAL_REPORT

    def test_round_complete_route(self):
        """测试轮次完成路由（默认）"""
        router = WorkflowRouter()
        state = {
            "current_round": 1,
            "open_issues": ["issue-1"],
            "awaiting_human_input": False,
        }

        result = router.route(state)
        assert result == RouteTarget.ROUND_SUMMARY

    def test_should_human_intervene(self):
        """测试是否需要人类介入判断"""
        router = WorkflowRouter(deadlock_opposition_ratio=0.3)

        # 无事件，不需要介入
        state1 = {"events": []}
        assert router.should_human_intervene(state1) is False

        # 无投票事件
        event1 = DiscussionEvent(
            event_type=EventType.ROLE_REVIEW,
            actor="architect",
            content="测试评审"
        )
        state2 = {"events": [event1]}
        assert router.should_human_intervene(state2) is False

        # 有投票，但反对票30%，不需要介入
        vote_event = DiscussionEvent(
            event_type=EventType.VOTE,
            actor="architect",
            content="赞成该提案",
            vote_result="赞成",
            target_issue="issue-1"
        )
        state3 = {"events": [vote_event]}
        assert router.should_human_intervene(state3) is False


class TestRoutingRule:
    """RoutingRule 测试类"""

    def test_rule_creation(self):
        """测试规则创建"""
        condition = lambda s: s.get("test") == True
        rule = RoutingRule(
            name="test_rule",
            condition=condition,
            priority=1,
            target=RouteTarget.CONTINUE,
        )

        assert rule.name == "test_rule"
        assert rule.priority == 1
        assert rule.condition({"test": True}) is True
