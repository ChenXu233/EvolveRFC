"""状态管理 - 事件溯源模式

基于事件的不可变状态管理，所有状态变更记录为事件。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TypedDict, Literal, Annotated, Optional
from operator import add


class EventType(Enum):
    """事件类型枚举"""
    ROLE_REVIEW = "role_review"          # 角色评审发言
    VOTE = "vote"                        # 投票行为
    HUMAN_INTERVENTION = "human"         # 人类干预
    HUMAN_DECISION = "human_decision"    # 人类最终决策
    CONSENSUS_REACHED = "consensus"      # 达成共识
    CLARIFICATION = "clarification"      # 书记官澄清
    ROUND_COMPLETE = "round_complete"    # 轮次完成


@dataclass
class DiscussionEvent:
    """讨论事件（不可变数据单元）"""
    event_type: EventType
    actor: str                           # 触发者：角色名称或 "human"
    content: str                         # 事件内容
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)  # 额外信息

    # 投票事件特有
    vote_result: Optional[Literal["赞成", "反对", "弃权"]] = None
    target_issue: Optional[str] = None   # 针对的议题ID

    # 人类干预特有
    human_action: Optional[Literal["意见注入", "参数调整", "强制通过", "强制驳回", "继续", "终止"]] = None


class ReviewOutput(TypedDict):
    """评审者输出结构"""
    论点: str
    论据: list[str]
    针对议题: str
    立场: Literal["赞成", "反对", "弃权"]
    置信度: float


class DiscussionState(TypedDict):
    """
    工作流状态（物化视图）

    所有字段从事件流派生，支持回溯和重放
    """
    # === 事件流（不可变，追加写入）===
    events: Annotated[list[DiscussionEvent], lambda x, y: x + y]

    # === 物化视图（从事件派生，可缓存）===
    rfc_content: str                      # 原始RFC内容
    max_rounds: int                       # 最大轮次（配置）
    current_round: int                    # 当前轮次
    current_focus: str                    # 当前轮次的争议焦点
    consensus_points: Annotated[list, add]  # 已达成共识的条目列表
    open_issues: Annotated[list, add]       # 待决议项列表（含正反方论点）

    # === 流程控制 ===
    awaiting_human_input: bool             # 是否暂停等待人类输入
    human_decision: Optional[dict]         # 人类决策结果
    last_human_action: Optional[str]       # 上次人类操作类型
    timeout_count: int                     # 超时次数
    workflow_status: Literal["讨论中", "待人类决策", "已完成", "已终止"]  # 工作流状态


def create_initial_state(rfc_content: str, max_rounds: int = 10) -> DiscussionState:
    """创建初始状态"""
    return DiscussionState(
        events=[],
        rfc_content=rfc_content,
        max_rounds=max_rounds,
        current_round=1,
        current_focus="",
        consensus_points=[],
        open_issues=[],
        awaiting_human_input=False,
        human_decision=None,
        last_human_action=None,
        timeout_count=0,
        workflow_status="讨论中",
    )


def add_event(state: DiscussionState, event: DiscussionEvent) -> DiscussionState:
    """添加事件到状态（不可变操作）"""
    new_events = state["events"] + [event]
    return DiscussionState(
        rfc_content=state["rfc_content"],
        max_rounds=state["max_rounds"],
        current_round=state["current_round"],
        current_focus=state["current_focus"],
        consensus_points=state["consensus_points"],
        open_issues=state["open_issues"],
        awaiting_human_input=state["awaiting_human_input"],
        human_decision=state["human_decision"],
        last_human_action=state["last_human_action"],
        timeout_count=state["timeout_count"],
        workflow_status=state["workflow_status"],
        events=new_events,
    )


def get_latest_events(state: DiscussionState, count: int = 10) -> list[DiscussionEvent]:
    """获取最近的N个事件"""
    return state["events"][-count:]
