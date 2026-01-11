"""状态管理 - 事件溯源模式

基于事件的不可变状态管理，所有状态变更记录为事件。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TypedDict, Literal, Annotated, Optional, List
from operator import add
import uuid


class ViewpointStatus(Enum):
    """观点状态枚举"""
    ACTIVE = "active"       # 活跃（待讨论）
    RESOLVED = "resolved"   # 已解决
    REJECTED = "rejected"   # 已拒绝


@dataclass
class Viewpoint:
    """观点（不可变数据单元）"""
    id: str                           # 唯一标识
    content: str                      # 核心观点（一句话）
    evidence: List[str]               # 论据列表
    proposer: str                     # 提出者
    status: ViewpointStatus           # 状态
    vote_count: dict                  # 投票统计 {"赞成": n, "反对": n, "弃权": n}
    created_round: int                # 创建轮次
    resolved_round: Optional[int] = None  # 解决轮次
    solutions: List[str] = field(default_factory=list)  # 解决方案列表
    arguments: List[dict] = field(default_factory=list)  # 论证/反驳列表
    proposed_solution: Optional[str] = None  # 建议的解决方案


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
    modified_rfc_content: Optional[str]   # 书记官根据通过的观点修改后的RFC
    max_rounds: int                       # 最大轮次（配置）
    current_round: int                    # 当前轮次
    current_focus: str                    # 当前轮次的争议焦点
    consensus_points: Annotated[list, add]  # 已达成共识的条目列表
    open_issues: Annotated[list, add]       # 待决议项列表（含正反方论点）

    # === 观点池机制 ===
    viewpoint_pool: Annotated[list[Viewpoint], add]  # 活跃观点池（最多3个）
    resolved_viewpoints: Annotated[list[Viewpoint], add]  # 已解决观点

    # === 流程控制 ===
    awaiting_human_input: bool             # 是否暂停等待人类输入
    human_decision: Optional[dict]         # 人类决策结果
    last_human_action: Optional[str]       # 上次人类操作类型
    timeout_count: int                     # 超时次数
    workflow_status: Literal["讨论中", "待人类决策", "已完成", "已终止", "RFC已通过"]  # 工作流状态

    # === RFC投票状态 ===
    rfc_modification_applied: bool         # 是否应用了RFC修改
    rfc_final_vote_results: Optional[list] # RFC最终投票结果
    rfc_final_vote_passed: Optional[bool]  # RFC是否通过


def create_initial_state(rfc_content: str, max_rounds: int = 10) -> DiscussionState:
    """创建初始状态"""
    return DiscussionState(
        events=[],
        rfc_content=rfc_content,
        modified_rfc_content=None,
        max_rounds=max_rounds,
        current_round=1,
        current_focus="",
        consensus_points=[],
        open_issues=[],
        viewpoint_pool=[],
        resolved_viewpoints=[],
        awaiting_human_input=False,
        human_decision=None,
        last_human_action=None,
        timeout_count=0,
        workflow_status="讨论中",
        rfc_modification_applied=False,
        rfc_final_vote_results=None,
        rfc_final_vote_passed=None,
    )


def add_event(state: DiscussionState, event: DiscussionEvent) -> DiscussionState:
    """添加事件到状态（不可变操作）"""
    new_events = state["events"] + [event]
    return DiscussionState(
        rfc_content=state["rfc_content"],
        modified_rfc_content=state.get("modified_rfc_content"),
        max_rounds=state["max_rounds"],
        current_round=state["current_round"],
        current_focus=state["current_focus"],
        consensus_points=state["consensus_points"],
        open_issues=state["open_issues"],
        viewpoint_pool=state["viewpoint_pool"],
        resolved_viewpoints=state["resolved_viewpoints"],
        awaiting_human_input=state["awaiting_human_input"],
        human_decision=state["human_decision"],
        last_human_action=state["last_human_action"],
        timeout_count=state["timeout_count"],
        workflow_status=state["workflow_status"],
        events=new_events,
        rfc_modification_applied=state.get("rfc_modification_applied", False),
        rfc_final_vote_results=state.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state.get("rfc_final_vote_passed"),
    )


def get_latest_events(state: DiscussionState, count: int = 10) -> list[DiscussionEvent]:
    """获取最近的N个事件"""
    return state["events"][-count:]


# === 观点池管理函数 ===

VIEWPOINT_POOL_LIMIT = 3  # 观点池上限


def can_add_viewpoint(state: DiscussionState) -> bool:
    """检查是否可以在观点池中添加新观点"""
    return len(state["viewpoint_pool"]) < VIEWPOINT_POOL_LIMIT


def create_viewpoint(
    content: str,
    evidence: List[str],
    proposer: str,
    created_round: int,
) -> Viewpoint:
    """创建新观点"""
    return Viewpoint(
        id=str(uuid.uuid4())[:8],
        content=content,
        evidence=evidence,
        proposer=proposer,
        status=ViewpointStatus.ACTIVE,
        vote_count={"赞成": 0, "反对": 0, "弃权": 0},
        created_round=created_round,
        resolved_round=None,
    )


def add_viewpoint_to_pool(state: DiscussionState, viewpoint: Viewpoint) -> DiscussionState:
    """将观点添加到观点池"""
    if not can_add_viewpoint(state):
        raise ValueError(f"观点池已满（最多{VIEWPOINT_POOL_LIMIT}个观点）")

    return DiscussionState(
        rfc_content=state["rfc_content"],
        modified_rfc_content=state.get("modified_rfc_content"),
        max_rounds=state["max_rounds"],
        current_round=state["current_round"],
        current_focus=state["current_focus"],
        consensus_points=state["consensus_points"],
        open_issues=state["open_issues"],
        viewpoint_pool=state["viewpoint_pool"] + [viewpoint],
        resolved_viewpoints=state["resolved_viewpoints"],
        awaiting_human_input=state["awaiting_human_input"],
        human_decision=state["human_decision"],
        last_human_action=state["last_human_action"],
        timeout_count=state["timeout_count"],
        workflow_status=state["workflow_status"],
        events=state["events"],
        rfc_modification_applied=state.get("rfc_modification_applied", False),
        rfc_final_vote_results=state.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state.get("rfc_final_vote_passed"),
    )


def vote_viewpoint(viewpoint: Viewpoint, vote_result: dict) -> Viewpoint:
    """为观点投票（返回新观点对象，不可变）"""
    updated_count = viewpoint.vote_count.copy()
    vote = vote_result.get("vote", "弃权")
    if vote in updated_count:
        updated_count[vote] += 1
    
    # 添加论证记录
    new_arguments = list(viewpoint.arguments)
    new_arguments.append({
        "actor": vote_result.get("actor", "unknown"),
        "content": vote_result.get("content", ""),
        "stance": vote,
        "round": vote_result.get("round", viewpoint.created_round),
    })
    
    return Viewpoint(
        id=viewpoint.id,
        content=viewpoint.content,
        evidence=viewpoint.evidence,
        proposer=viewpoint.proposer,
        status=viewpoint.status,
        vote_count=updated_count,
        created_round=viewpoint.created_round,
        resolved_round=viewpoint.resolved_round,
        solutions=viewpoint.solutions,
        arguments=new_arguments,
    )


def resolve_viewpoint(viewpoint: Viewpoint, resolved_round: int, status: ViewpointStatus = ViewpointStatus.RESOLVED, solution: Optional[str] = None) -> Viewpoint:
    """标记观点为已解决（返回新观点对象，不可变）"""
    updated_solutions = list(viewpoint.solutions)
    if solution:
        updated_solutions.append(solution)
    
    return Viewpoint(
        id=viewpoint.id,
        content=viewpoint.content,
        evidence=viewpoint.evidence,
        proposer=viewpoint.proposer,
        status=status,
        vote_count=viewpoint.vote_count,
        created_round=viewpoint.created_round,
        resolved_round=resolved_round,
        solutions=updated_solutions,
        arguments=viewpoint.arguments,
    )


def check_viewpoint_resolved(viewpoint: Viewpoint, total_reviewers: int) -> bool:
    """检查观点是否已解决（多数赞成 = 解决）"""
    if viewpoint.status != ViewpointStatus.ACTIVE:
        return True

    yes_votes = viewpoint.vote_count.get("赞成", 0)
    no_votes = viewpoint.vote_count.get("反对", 0)

    # 多数赞成且赞成票数 > 反对票数
    return yes_votes > no_votes and yes_votes > total_reviewers // 2


def resolve_active_viewpoints(state: DiscussionState, current_round: int) -> DiscussionState:
    """检查并解决观点池中的已解决观点"""
    reviewers_count = 4  # 默认4个评审者（architect, security, cost_control, innovator）
    active_viewpoints = []
    resolved_viewpoints = list(state["resolved_viewpoints"])

    for vp in state["viewpoint_pool"]:
        if check_viewpoint_resolved(vp, reviewers_count):
            resolved_viewpoints.append(resolve_viewpoint(vp, current_round))
        else:
            active_viewpoints.append(vp)

    return DiscussionState(
        rfc_content=state["rfc_content"],
        modified_rfc_content=state.get("modified_rfc_content"),
        max_rounds=state["max_rounds"],
        current_round=state["current_round"],
        current_focus=state["current_focus"],
        consensus_points=state["consensus_points"],
        open_issues=state["open_issues"],
        viewpoint_pool=active_viewpoints,
        resolved_viewpoints=resolved_viewpoints,
        awaiting_human_input=state["awaiting_human_input"],
        human_decision=state["human_decision"],
        last_human_action=state["last_human_action"],
        timeout_count=state["timeout_count"],
        workflow_status=state["workflow_status"],
        events=state["events"],
        rfc_modification_applied=state.get("rfc_modification_applied", False),
        rfc_final_vote_results=state.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state.get("rfc_final_vote_passed"),
    )


def format_viewpoint_pool(viewpoint_pool: list[Viewpoint]) -> str:
    """格式化观点池为可读字符串"""
    if not viewpoint_pool:
        return "当前无活跃观点"

    lines = []
    for i, vp in enumerate(viewpoint_pool, 1):
        status_icon = "🔴" if vp.status == ViewpointStatus.ACTIVE else "🟢"
        votes = f"👍{vp.vote_count.get('赞成', 0)} 👎{vp.vote_count.get('反对', 0)}"
        lines.append(f"{status_icon} 观点{i}: {vp.content}")
        lines.append(f"   提出者: {vp.proposer} | 投票: {votes}")
        
        # 显示论据
        if vp.evidence:
            evidence_str = "; ".join(vp.evidence[:2])
            lines.append(f"   论据: {evidence_str}")
        
        # 显示论证/反驳
        if vp.arguments:
            lines.append("   论证:")
            for arg in vp.arguments[-3:]:  # 只显示最近3条
                stance_icon = "👍" if arg.get("stance") == "赞成" else "👎" if arg.get("stance") == "反对" else "🤔"
                lines.append(f"     {stance_icon} {arg.get('actor', '?')}: {arg.get('content', '')[:50]}...")
        
        # 显示解决方案
        if vp.solutions:
            lines.append("   解决方案:")
            for sol in vp.solutions:
                lines.append(f"     ✓ {sol[:50]}...")

    return "\n".join(lines)
