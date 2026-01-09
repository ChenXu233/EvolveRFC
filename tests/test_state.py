"""状态管理单元测试
"""

import pytest
from datetime import datetime

from evolve_rfc.core.state import (
    DiscussionEvent,
    DiscussionState,
    EventType,
    create_initial_state,
    add_event,
    get_latest_events,
)


class TestDiscussionEvent:
    """DiscussionEvent 测试类"""

    def test_event_creation(self):
        """测试事件创建"""
        event = DiscussionEvent(
            event_type=EventType.ROLE_REVIEW,
            actor="architect",
            content="测试内容"
        )
        assert event.event_type == EventType.ROLE_REVIEW
        assert event.actor == "architect"
        assert event.content == "测试内容"
        assert event.timestamp is not None

    def test_vote_event(self):
        """测试投票事件"""
        event = DiscussionEvent(
            event_type=EventType.VOTE,
            actor="architect",
            content="赞成该提案",
            vote_result="赞成",
            target_issue="issue-1"
        )
        assert event.vote_result == "赞成"
        assert event.target_issue == "issue-1"

    def test_human_intervention_event(self):
        """测试人类干预事件"""
        event = DiscussionEvent(
            event_type=EventType.HUMAN_INTERVENTION,
            actor="human",
            content="建议增加日志记录",
            human_action="意见注入"
        )
        assert event.human_action == "意见注入"


class TestDiscussionState:
    """DiscussionState 测试类"""

    def test_create_initial_state(self):
        """测试创建初始状态"""
        state = create_initial_state("RFC内容", max_rounds=5)

        assert state["rfc_content"] == "RFC内容"
        assert state["max_rounds"] == 5
        assert state["current_round"] == 1
        assert state["events"] == []
        assert state["workflow_status"] == "讨论中"

    def test_add_event(self):
        """测试添加事件"""
        state = create_initial_state("RFC内容")
        event = DiscussionEvent(
            event_type=EventType.ROLE_REVIEW,
            actor="architect",
            content="测试评审"
        )

        new_state = add_event(state, event)

        assert len(new_state["events"]) == 1
        assert new_state["events"][0].actor == "architect"
        # 原始状态不变
        assert len(state["events"]) == 0

    def test_get_latest_events(self):
        """测试获取最新事件"""
        state = create_initial_state("RFC内容")

        # 添加多个事件
        for i in range(5):
            event = DiscussionEvent(
                event_type=EventType.ROLE_REVIEW,
                actor=f"role-{i}",
                content=f"内容 {i}"
            )
            state = add_event(state, event)

        # 获取最近3个
        latest = get_latest_events(state, count=3)
        assert len(latest) == 3
        assert latest[0].actor == "role-2"
        assert latest[2].actor == "role-4"
