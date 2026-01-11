"""工作流节点定义
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from contextvars import ContextVar
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..settings import get_role_llm_config, BaseLLMConfig
from ..core.state import (
    DiscussionState,
    DiscussionEvent,
    EventType,
    add_event,
    Viewpoint,
    create_viewpoint,
    resolve_active_viewpoints,
    VIEWPOINT_POOL_LIMIT,
)
from ..agents import get_role_prompt, get_reviewer_roles
from ..shared import run_review_with_viewpoint_pool, run_review_with_tools
from ..shared.tools import cleanup_tool_context, set_viewpoint_pool_for_tool


# 全局 LLM 客户端缓存
_llm_clients: dict[str, ChatOpenAI | ChatAnthropic] = {}

# === 上下文变量用于 UI 回调 ===
# 这些变量允许外部（如 UI）设置回调函数，节点内部会调用这些回调
stream_callback_var: ContextVar[Optional[Callable[[str, str], None]]] = ContextVar(
    "stream_callback", default=None
)
token_callback_var: ContextVar[Optional[Callable[[dict], None]]] = ContextVar(
    "token_callback", default=None
)
log_callback_var: ContextVar[Optional[Callable[[str], None]]] = ContextVar(
    "log_callback", default=None
)
workflow_state_callback_var: ContextVar[Optional[Callable[[str, int, dict], None]]] = ContextVar(
    "workflow_state_callback", default=None
)
finish_callback_var: ContextVar[Optional[Callable[[str, list], None]]] = ContextVar(
    "finish_callback", default=None
)
# 用于实时停止检查的标志变量
_review_running_var: ContextVar[bool] = ContextVar("review_running", default=True)


def _log_message(msg: str):
    """发送日志消息到 UI"""
    callback = log_callback_var.get()
    if callback:
        callback(msg)


def _update_workflow_state(stage: str, round_num: int, role_data: dict = {}):
    """更新工作流状态到 UI"""
    callback = workflow_state_callback_var.get()
    if callback:
        callback(stage, round_num, role_data or {})


def _on_review_start(role: str, round_num: int):
    """评审开始时调用"""
    _update_workflow_state("parallel_review", round_num, {"role": role, "status": "speaking"})


def _on_review_end(role: str, round_num: int, vote: str = "弃权"):
    """评审结束时调用"""
    _update_workflow_state("parallel_review", round_num, {"role": role, "status": "done", "vote": vote})


def _create_llm_client(
    role_name: str, config: BaseLLMConfig
) -> ChatOpenAI | ChatAnthropic:
    """根据配置创建 LLM 客户端"""
    if not config.api_key:
        raise ValueError(f"角色 {role_name} 的 LLM 配置缺少 API 密钥")

    if config.provider == "openai":
        return ChatOpenAI(
            model=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
            api_key=config.api_key,
        )
    elif config.provider == "anthropic":
        return ChatAnthropic(
            model_name=config.model,
            temperature=config.temperature,
            base_url=config.base_url,
            timeout=config.timeout,
            stop=config.stop,
            api_key=config.api_key,
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
        _llm_clients[key] = _create_llm_client(role_name or "architect", config)

    return _llm_clients[key]


def init_node(state: DiscussionState) -> DiscussionState:
    """初始化节点"""
    return state


# === 配置控制 ===
# 是否启用多段思考（工具调用）
ENABLE_MULTI_STEP_THINKING = True


def parallel_review_node(state: DiscussionState) -> DiscussionState:
    """并行评审节点 - 多个角色顺序评审，每个角色实时显示输出，集成观点池
    
    如果 ENABLE_MULTI_STEP_THINKING 为 True，则使用 ReAct Agent 进行多段思考评审，
    支持调用工具（文件读取、代码搜索等）来获取更多信息。
    """
    rfc_content = state["rfc_content"]
    current_round = state["current_round"]
    viewpoint_pool = state["viewpoint_pool"]

    # 获取外部回调
    external_stream_cb = stream_callback_var.get()
    external_token_cb = token_callback_var.get()
    external_finish_cb = finish_callback_var.get()

    def stream_callback(role: str, chunk: str):
        """流式输出回调"""
        if external_stream_cb:
            external_stream_cb(role, chunk)

    # 使用带观点池的评审逻辑
    review_results = []

    # 在开始评审前清理工具上下文（防止数据残留）
    cleanup_tool_context()

    for role in get_reviewer_roles():
        # 通知 UI 评审开始
        _on_review_start(role, current_round)

        # 在每个角色评审开始前清理工具上下文
        cleanup_tool_context()

        # 设置观点池上下文，让工具可以读取当前观点池
        set_viewpoint_pool_for_tool(list(viewpoint_pool))

        # 创建流式回调包装器
        def make_callback(rl: str) -> Callable[[str], None]:
            def callback(chunk: str) -> None:
                stream_callback(rl, chunk)
            return callback

        role_callback = make_callback(role)

        # 创建 token 回调包装器
        def make_token_callback(rl: str) -> Callable[[dict], None]:
            def callback(token_data: dict) -> None:
                token_data["role"] = rl
                if external_token_cb:
                    external_token_cb(token_data)
            return callback

        role_token_callback = make_token_callback(role)

        try:
            # 根据配置选择评审函数
            if ENABLE_MULTI_STEP_THINKING:
                # 使用多段思考评审（ReAct Agent，支持工具调用）
                # 创建停止检查回调：实时检查停止标志
                def stop_check() -> bool:
                    return not _review_running_var.get()
                
                result = run_review_with_tools(
                    role=role,
                    content=rfc_content,
                    current_round=current_round,
                    viewpoint_pool=viewpoint_pool,
                    stream_callback=role_callback,
                    previous_results=review_results,
                    token_callback=role_token_callback,
                    stop_check_callback=stop_check,  # 实时停止检查
                )
            else:
                # 使用普通评审（单次 LLM 调用）
                # 创建停止检查回调
                def stop_check() -> bool:
                    return not _review_running_var.get()
                
                result = run_review_with_viewpoint_pool(
                    role=role,
                    content=rfc_content,
                    current_round=current_round,
                    viewpoint_pool=viewpoint_pool,
                    stream_callback=role_callback,
                    previous_results=review_results,
                    token_callback=role_token_callback,
                    stop_check_callback=stop_check,  # 实时停止检查
                )
            review_results.append(result)
        except Exception as e:
            review_results.append({
                "role": role,
                "content": f"评审失败：{str(e)}",
                "vote": "弃权",
                "new_viewpoints": [],
            })

        # 通知 UI 评审结束
        last_vote = review_results[-1].get("vote") if review_results else "弃权"
        last_tool_calls = review_results[-1].get("tool_calls", []) if review_results else []
        _on_review_end(role, current_round, last_vote)
        
        # 调用 finish 回调，显示工具调用信息
        if external_finish_cb:
            external_finish_cb(role, last_tool_calls)

        # 实时停止检查：每个角色评审完成后立即检查停止信号
        if not _review_running_var.get():
            _log_message(f"⏹ 评审在角色 {role} 完成后停止")
            # 保存当前状态用于断点续传
            try:
                save_workflow_state(state, "manual_stop")
                _log_message("💾 状态已保存，可用于断点续传")
            except Exception as e:
                _log_message(f"⚠️ 状态保存失败: {e}")
            return state

    # 收集所有新事件
    new_events = []
    for result in review_results:
        role = result.get("role", "未知")
        vote = result.get("vote")
        
        # 生成评审事件
        new_events.append(DiscussionEvent(
            event_type=EventType.ROLE_REVIEW,
            actor=role,
            content=result.get("content", ""),
            metadata={"round": current_round},
            vote_result=vote,  # 包含投票结果
        ))

    # 收集所有新观点（限制：每人每轮1个，总量不超过池上限）
    new_viewpoints = []
    current_pool_size = len(state["viewpoint_pool"])
    role_viewpoint_count: dict[str, int] = {}  # 记录每个角色本轮已提出观点数

    for result in review_results:
        role = result.get("role", "未知")

        # 该角色本轮已提出过观点，跳过
        if role_viewpoint_count.get(role, 0) >= 1:
            continue

        # 观点池已满，跳过
        if current_pool_size + len(new_viewpoints) >= VIEWPOINT_POOL_LIMIT:
            break

        # 只取该角色的第一个观点
        vp_data_list = result.get("new_viewpoints", [])
        if not vp_data_list:
            continue

        # 只取第一个观点
        vp_data = vp_data_list[0]
        new_viewpoints.append(create_viewpoint(
            content=vp_data.get("content", ""),
            evidence=vp_data.get("evidence", []),
            proposer=role,
            created_round=current_round,
        ))
        role_viewpoint_count[role] = 1

    # 同步观点回应到观点池（更新 arguments）
    updated_pool = list(state["viewpoint_pool"])  # 复制当前观点池
    for result in review_results:
        role = result.get("role", "未知")
        tool_calls = result.get("tool_calls", [])

        for tc in tool_calls:
            if tc.get("tool") == "respond_to_viewpoint":
                args = tc.get("arguments", {})
                vp_id = args.get("viewpoint_id", "")
                stance = args.get("stance", "")
                response = args.get("response", "")

                # 找到对应的观点并更新
                for i, vp in enumerate(updated_pool):
                    if vp.id == vp_id:
                        # 添加论证记录
                        new_arguments = list(vp.arguments)
                        new_arguments.append({
                            "actor": role,
                            "content": response,
                            "stance": stance,
                            "round": current_round,
                        })

                        # 更新投票统计
                        new_vote_count = vp.vote_count.copy()
                        if stance in new_vote_count:
                            new_vote_count[stance] += 1

                        # 创建更新后的观点
                        from ..core.state import Viewpoint as VPClass
                        updated_vp = VPClass(
                            id=vp.id,
                            content=vp.content,
                            evidence=vp.evidence,
                            proposer=vp.proposer,
                            status=vp.status,
                            vote_count=new_vote_count,
                            created_round=vp.created_round,
                            resolved_round=vp.resolved_round,
                            solutions=vp.solutions,
                            arguments=new_arguments,
                        )
                        updated_pool[i] = updated_vp
                        break  # 找到一个就停止

    # 构建最终状态（只返回一次状态更新）
    result_state = DiscussionState(
        events=state["events"] + new_events,
        rfc_content=state["rfc_content"],
        modified_rfc_content=state.get("modified_rfc_content"),
        max_rounds=state["max_rounds"],
        current_round=state["current_round"],
        current_focus=state["current_focus"],
        consensus_points=state["consensus_points"],
        open_issues=state["open_issues"],
        viewpoint_pool=updated_pool + new_viewpoints,
        resolved_viewpoints=state["resolved_viewpoints"],
        awaiting_human_input=state["awaiting_human_input"],
        human_decision=state["human_decision"],
        last_human_action=state["last_human_action"],
        timeout_count=state["timeout_count"],
        workflow_status=state["workflow_status"],
        rfc_modification_applied=state.get("rfc_modification_applied", False),
        rfc_final_vote_results=state.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state.get("rfc_final_vote_passed"),
    )

    return result_state


def add_viewpoint_to_pool(state: DiscussionState, viewpoint: Viewpoint) -> DiscussionState:
    """将观点添加到观点池（不可变操作）"""
    if len(state["viewpoint_pool"]) >= VIEWPOINT_POOL_LIMIT:
        return state  # 观点池已满，不添加

    return DiscussionState(
        events=state["events"],
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
        rfc_modification_applied=state.get("rfc_modification_applied", False),
        rfc_final_vote_results=state.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state.get("rfc_final_vote_passed"),
    )


def vote_analyzer_node(state: DiscussionState) -> DiscussionState:
    """投票统计与分歧分析节点"""
    events = state["events"]
    current_round = state["current_round"]

    # 收集本轮评审事件（包含投票结果）
    review_events = [
        e for e in events
        if e.event_type == EventType.ROLE_REVIEW 
        and e.metadata.get("round") == current_round
        and e.vote_result  # 只收集有投票结果的事件
    ]

    # 计算投票分布
    if review_events:
        vote_results = [e.vote_result for e in review_events if e.vote_result]
        if vote_results:
            yes_votes = vote_results.count("赞成")
            no_votes = vote_results.count("反对")
            abstain_votes = vote_results.count("弃权")

            # 检查是否需要人类介入（反对票 > 30%）
            total_votes = len(vote_results)
            needs_human = (no_votes / total_votes) > 0.3 if total_votes > 0 else False

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


def viewpoint_pool_manager_node(state: DiscussionState) -> DiscussionState:
    """观点池管理器节点 - 检查观点解决情况，决定下一步流程"""
    current_round = state["current_round"]

    # 检查并解决已达成共识的观点
    state = resolve_active_viewpoints(state, current_round)

    # 统计解决情况
    active_count = len(state["viewpoint_pool"])
    resolved_count = len(state["resolved_viewpoints"])

    # 添加观点池状态事件
    pool_status_event = DiscussionEvent(
        event_type=EventType.ROUND_COMPLETE,
        actor="system",
        content=f"观点池状态：活跃 {active_count}/{VIEWPOINT_POOL_LIMIT}，已解决 {resolved_count}",
        metadata={
            "round": current_round,
            "viewpoint_pool_status": {
                "active": active_count,
                "resolved": resolved_count,
                "limit": VIEWPOINT_POOL_LIMIT,
            },
        },
    )
    state = add_event(state, pool_status_event)

    return state


def human_oversight_node(state: DiscussionState) -> DiscussionState:
    """人类监督节点 - 工作流暂停，等待人类输入"""
    return state


def clerk_summary_node(state: DiscussionState) -> DiscussionState:
    """书记官总结节点 - 汇总讨论结果，包含观点池统计"""
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

    # 添加观点池统计
    active_viewpoints = state["viewpoint_pool"]
    resolved_viewpoints = state["resolved_viewpoints"]

    input_text += "\n=== 观点池统计 ==="
    input_text += f"\n活跃观点数：{len(active_viewpoints)}/{VIEWPOINT_POOL_LIMIT}"
    input_text += f"\n已解决观点数：{len(resolved_viewpoints)}"

    if active_viewpoints:
        input_text += "\n当前活跃观点："
        for i, vp in enumerate(active_viewpoints, 1):
            votes = f"👍{vp.vote_count.get('赞成', 0)} 👎{vp.vote_count.get('反对', 0)}"
            input_text += f"\n  {i}. [{vp.id}] {vp.content} ({votes})"

    if resolved_viewpoints:
        input_text += "\n已解决观点："
        for vp in resolved_viewpoints[-3:]:  # 只显示最近3个
            input_text += f"\n  ✓ [{vp.id}] {vp.content} (第{vp.resolved_round}轮解决)"

    input_text += f"\n\n当前共识点：{state['consensus_points']}"
    input_text += f"\n待决议项：{state['open_issues']}"

    try:
        response = client.invoke([
            SystemMessage(content=get_role_prompt("clerk")),
            HumanMessage(content=input_text),
        ])
        response_content = response.content
        # 确保 content 是字符串类型
        content = str(response_content) if not isinstance(response_content, str) else response_content

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


def clerk_rfc_modify_node(state: DiscussionState) -> DiscussionState:
    """书记官RFC修改节点 - 根据已通过的观点修改RFC原文

    规则：观点获得2票赞成且赞成>反对时视为通过，书记官据此修改RFC
    """
    client = get_llm_client("clerk")
    current_round = state["current_round"]
    original_rfc = state["rfc_content"]
    resolved_viewpoints = state.get("resolved_viewpoints", [])

    # 检查本轮是否有新解决的观点
    new_resolved = [vp for vp in resolved_viewpoints
                    if vp.resolved_round == current_round]

    if not new_resolved:
        # 没有新解决的观点，无需修改RFC
        state["modified_rfc_content"] = original_rfc
        state["rfc_modification_applied"] = False

        no_mod_event = DiscussionEvent(
            event_type=EventType.CLARIFICATION,
            actor="clerk",
            content=f"第{current_round}轮无新通过观点，RFC保持不变",
            metadata={"round": current_round, "modification": "none"},
        )
        state = add_event(state, no_mod_event)
        return state

    # 构建修改提示
    input_text = f"""你是RFC评审的书记官。根据本轮通过的{len(new_resolved)}个观点，请修改RFC原文。

## 原始RFC：
{original_rfc[:3000]}...

## 本轮通过的观点及解决方案：
"""

    for i, vp in enumerate(new_resolved, 1):
        input_text += f"""
{i}. 观点：{vp.content}
   证据：{vp.evidence}
   建议方案：{vp.proposed_solution}
"""

    input_text += """
## 任务要求：
1. 根据通过的观点击RFC原文进行最小必要修改
2. 只修改与观点相关的内容，不要过度修改
3. 保持RFC的整体结构和格式
4. 输出修改后的完整RFC内容

请输出修改后的完整RFC："""

    try:
        response = client.invoke([
            SystemMessage(content=get_role_prompt("clerk")),
            HumanMessage(content=input_text),
        ])
        response_content = response.content
        modified_rfc = str(response_content) if not isinstance(response_content, str) else response_content

        # 更新状态
        state["modified_rfc_content"] = modified_rfc
        state["rfc_modification_applied"] = True

        # 添加修改事件
        mod_event = DiscussionEvent(
            event_type=EventType.CLARIFICATION,
            actor="clerk",
            content=f"第{current_round}轮RFC已根据{len(new_resolved)}个通过观点修改",
            metadata={
                "round": current_round,
                "modification": "applied",
                "resolved_viewpoints": [vp.id for vp in new_resolved],
                "diff_summary": f"应用了{len(new_resolved)}个观点的修改建议"
            },
        )
        state = add_event(state, mod_event)

    except Exception as e:
        # 修改失败，保持原RFC
        state["modified_rfc_content"] = original_rfc
        state["rfc_modification_applied"] = False

        error_event = DiscussionEvent(
            event_type=EventType.CLARIFICATION,
            actor="clerk",
            content=f"RFC修改失败，保持原文：{str(e)}",
            metadata={"round": current_round, "modification": "failed"},
        )
        state = add_event(state, error_event)

    return state


def rfc_vote_node(state: DiscussionState) -> DiscussionState:
    """RFC投票节点 - 各模型对修改后的RFC进行通过/不通过投票

    这是针对RFC整体是否通过的投票，不是针对具体观点的投票。
    """
    current_round = state["current_round"]
    modified_rfc = state.get("modified_rfc_content", state["rfc_content"])

    # 收集各角色的投票
    vote_results: list[dict] = []
    roles = get_all_reviewer_roles()

    # 构建投票提示
    rfc_for_vote = modified_rfc if modified_rfc else state["rfc_content"]
    vote_prompt = f"""请对修改后的RFC进行最终投票表决。

## 修改后的RFC内容：
{rfc_for_vote[:4000]}...

## 评审历史：
- 已通过观点数：{len(state.get('resolved_viewpoints', []))}
- 当前轮次：{current_round}
- 活跃观点数：{len(state.get('viewpoint_pool', []))}

## 投票要求：
请对整体RFC是否通过给出明确立场：
- **赞成**：RFC经过修改后符合要求，可以接受
- **反对**：RFC仍存在重大问题，需要继续修改
- **弃权**：不确定，需要更多信息

请只输出一个词：赞成、反对 或 弃权"""

    for role in roles:
        try:
            client = get_llm_client(role)
            response = client.invoke([
                SystemMessage(content=get_role_prompt(role)),
                HumanMessage(content=f"你正在参与RFC最终投票。\n\n{vote_prompt}"),
            ])
            response_content = response.content
            vote_text = str(response_content).strip()

            # 解析投票
            if "赞成" in vote_text and "反对" not in vote_text:
                vote = "赞成"
            elif "反对" in vote_text:
                vote = "反对"
            else:
                vote = "弃权"

            vote_result = {
                "voter": role,
                "issue_id": "RFC_FINAL_VOTE",
                "vote": vote,
                "reason": vote_text[:200],
            }
            vote_results.append(vote_result)

        except Exception as e:
            # 投票失败默认为弃权
            vote_result = {
                "voter": role,
                "issue_id": "RFC_FINAL_VOTE",
                "vote": "弃权",
                "reason": f"投票失败：{str(e)}",
            }
            vote_results.append(vote_result)

    # 统计投票
    yes_votes = sum(1 for r in vote_results if r["vote"] == "赞成")
    no_votes = sum(1 for r in vote_results if r["vote"] == "反对")
    abstain_votes = sum(1 for r in vote_results if r["vote"] == "弃权")

    # 判断是否通过（简单多数赞成）
    rfc_passed = yes_votes > no_votes

    # 添加投票事件
    vote_event = DiscussionEvent(
        event_type=EventType.VOTE,
        actor="system",
        content=f"RFC最终投票结果：赞成{yes_votes}，反对{no_votes}，弃权{abstain_votes} - {'通过' if rfc_passed else '未通过'}",
        metadata={
            "round": current_round,
            "vote_summary": {"赞成": yes_votes, "反对": no_votes, "弃权": abstain_votes},
            "rfc_passed": rfc_passed,
            "vote_results": vote_results,
        },
        vote_result="赞成" if rfc_passed else "反对",
    )
    state = add_event(state, vote_event)

    # 更新状态
    state["rfc_final_vote_results"] = vote_results
    state["rfc_final_vote_passed"] = rfc_passed

    if rfc_passed:
        state["workflow_status"] = "RFC已通过"
    else:
        state["workflow_status"] = "讨论中"

    return state


def get_all_reviewer_roles() -> list[str]:
    """获取所有评审者角色（从配置动态读取）"""
    return get_reviewer_roles()


# === 状态保存/加载功能 ===

# 保存状态文件路径
WORKFLOW_STATE_DIR = Path("workflow_states")


def serialize_datetime(obj):
    """序列化 datetime 对象"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def serialize_state(state: DiscussionState, reason: str = "manual") -> dict:
    """将状态序列化为可保存的字典"""

    # 序列化事件
    events_data = []
    for event in state.get("events", []):
        event_dict = {
            "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
            "actor": event.actor,
            "content": event.content,
            "timestamp": serialize_datetime(event.timestamp) if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
            "metadata": event.metadata,
        }
        if hasattr(event, 'vote_result'):
            event_dict["vote_result"] = event.vote_result
        if hasattr(event, 'target_issue'):
            event_dict["target_issue"] = event.target_issue
        if hasattr(event, 'human_action'):
            event_dict["human_action"] = event.human_action
        events_data.append(event_dict)
    
    # 序列化观点池
    viewpoint_pool_data = []
    for vp in state.get("viewpoint_pool", []):
        viewpoint_pool_data.append({
            "id": vp.id,
            "content": vp.content,
            "evidence": vp.evidence,
            "proposer": vp.proposer,
            "status": vp.status.value if hasattr(vp.status, 'value') else vp.status,
            "vote_count": vp.vote_count,
            "created_round": vp.created_round,
            "resolved_round": vp.resolved_round,
            "solutions": vp.solutions,
            "arguments": vp.arguments,
        })
    
    # 序列化已解决观点
    resolved_viewpoints_data = []
    for vp in state.get("resolved_viewpoints", []):
        resolved_viewpoints_data.append({
            "id": vp.id,
            "content": vp.content,
            "evidence": vp.evidence,
            "proposer": vp.proposer,
            "status": vp.status.value if hasattr(vp.status, 'value') else vp.status,
            "vote_count": vp.vote_count,
            "created_round": vp.created_round,
            "resolved_round": vp.resolved_round,
            "solutions": vp.solutions,
            "arguments": vp.arguments,
        })
    
    return {
        "version": "1.0",
        "saved_at": datetime.now().isoformat(),
        "save_reason": reason,
        "state": {
            "rfc_content": state.get("rfc_content", ""),
            "modified_rfc_content": state.get("modified_rfc_content"),
            "max_rounds": state.get("max_rounds", 10),
            "current_round": state.get("current_round", 1),
            "current_focus": state.get("current_focus", ""),
            "consensus_points": state.get("consensus_points", []),
            "open_issues": state.get("open_issues", []),
            "viewpoint_pool": viewpoint_pool_data,
            "resolved_viewpoints": resolved_viewpoints_data,
            "awaiting_human_input": state.get("awaiting_human_input", False),
            "human_decision": state.get("human_decision", None),
            "last_human_action": state.get("last_human_action", None),
            "timeout_count": state.get("timeout_count", 0),
            "workflow_status": state.get("workflow_status", "讨论中"),
            "events": events_data,
        }
    }


def deserialize_state(data: dict) -> DiscussionState:
    """从字典反序列化为 DiscussionState"""
    from ..core.state import ViewpointStatus, DiscussionEvent
    
    state_data = data.get("state", data)
    
    # 反序列化事件
    events = []
    for event_dict in state_data.get("events", []):
        event_type_str = event_dict.get("event_type", "role_review")
        # 将字符串转换为 EventType 枚举
        try:
            if isinstance(event_type_str, str):
                event_type = EventType(event_type_str)
            else:
                event_type = event_type_str
        except ValueError:
            event_type = EventType.ROLE_REVIEW
        
        timestamp = event_dict.get("timestamp", datetime.now())
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now()
        
        event = DiscussionEvent(
            event_type=event_type,
            actor=event_dict.get("actor", "unknown"),
            content=event_dict.get("content", ""),
            timestamp=timestamp,
            metadata=event_dict.get("metadata", {}),
            vote_result=event_dict.get("vote_result", None),
            target_issue=event_dict.get("target_issue", None),
            human_action=event_dict.get("human_action", None),
        )
        events.append(event)
    
    # 反序列化观点池
    viewpoint_pool = []
    for vp_dict in state_data.get("viewpoint_pool", []):
        status_str = vp_dict.get("status", "active")
        try:
            if isinstance(status_str, str):
                status = ViewpointStatus(status_str)
            else:
                status = status_str
        except ValueError:
            status = ViewpointStatus.ACTIVE
        
        vp = Viewpoint(
            id=vp_dict.get("id", ""),
            content=vp_dict.get("content", ""),
            evidence=vp_dict.get("evidence", []),
            proposer=vp_dict.get("proposer", ""),
            status=status,
            vote_count=vp_dict.get("vote_count", {"赞成": 0, "反对": 0, "弃权": 0}),
            created_round=vp_dict.get("created_round", 1),
            resolved_round=vp_dict.get("resolved_round", None),
            solutions=vp_dict.get("solutions", []),
            arguments=vp_dict.get("arguments", []),
        )
        viewpoint_pool.append(vp)
    
    # 反序列化已解决观点
    resolved_viewpoints = []
    for vp_dict in state_data.get("resolved_viewpoints", []):
        status_str = vp_dict.get("status", "resolved")
        try:
            if isinstance(status_str, str):
                status = ViewpointStatus(status_str)
            else:
                status = status_str
        except ValueError:
            status = ViewpointStatus.RESOLVED
        
        vp = Viewpoint(
            id=vp_dict.get("id", ""),
            content=vp_dict.get("content", ""),
            evidence=vp_dict.get("evidence", []),
            proposer=vp_dict.get("proposer", ""),
            status=status,
            vote_count=vp_dict.get("vote_count", {"赞成": 0, "反对": 0, "弃权": 0}),
            created_round=vp_dict.get("created_round", 1),
            resolved_round=vp_dict.get("resolved_round", None),
            solutions=vp_dict.get("solutions", []),
            arguments=vp_dict.get("arguments", []),
        )
        resolved_viewpoints.append(vp)

    return DiscussionState(
        events=events,
        rfc_content=state_data.get("rfc_content", ""),
        modified_rfc_content=state_data.get("modified_rfc_content"),
        max_rounds=state_data.get("max_rounds", 10),
        current_round=state_data.get("current_round", 1),
        current_focus=state_data.get("current_focus", ""),
        consensus_points=state_data.get("consensus_points", []),
        open_issues=state_data.get("open_issues", []),
        viewpoint_pool=viewpoint_pool,
        resolved_viewpoints=resolved_viewpoints,
        awaiting_human_input=state_data.get("awaiting_human_input", False),
        human_decision=state_data.get("human_decision", None),
        last_human_action=state_data.get("last_human_action", None),
        timeout_count=state_data.get("timeout_count", 0),
        workflow_status=state_data.get("workflow_status", "讨论中"),
        rfc_modification_applied=state_data.get("rfc_modification_applied", False),
        rfc_final_vote_results=state_data.get("rfc_final_vote_results"),
        rfc_final_vote_passed=state_data.get("rfc_final_vote_passed"),
    )


def save_workflow_state(state: DiscussionState, reason: str = "manual") -> str:
    """保存工作流状态到 JSON 文件
    
    Args:
        state: 当前工作流状态
        reason: 保存原因（"manual" 或 "auto"）
    
    Returns:
        保存的文件路径
    """
    WORKFLOW_STATE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 生成文件名：时间戳_原因.json
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"workflow_state_{timestamp}_{reason}.json"
    filepath = WORKFLOW_STATE_DIR / filename
    
    # 序列化状态
    data = serialize_state(state, reason)
    
    # 保存到文件
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return str(filepath)


def load_workflow_state(filepath: str) -> tuple[DiscussionState, str]:
    """从 JSON 文件加载工作流状态
    
    Args:
        filepath: 状态文件路径
    
    Returns:
        (状态对象, 保存原因)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    state = deserialize_state(data)
    reason = data.get("save_reason", "unknown")
    
    return state, reason


def get_latest_saved_state() -> tuple[str | None, DiscussionState | None, str | None]:
    """获取最新的保存状态
    
    Returns:
        (文件路径, 状态对象, 保存原因) 或 (None, None, None) 如果没有保存的状态
    """
    if not WORKFLOW_STATE_DIR.exists():
        return None, None, None
    
    # 查找所有状态文件
    state_files = list(WORKFLOW_STATE_DIR.glob("workflow_state_*.json"))
    if not state_files:
        return None, None, None
    
    # 按修改时间排序，取最新的
    latest_file = max(state_files, key=lambda f: f.stat().st_mtime)
    
    try:
        state, reason = load_workflow_state(str(latest_file))
        return str(latest_file), state, reason
    except Exception as e:
        _log_message(f"⚠️ 加载保存的状态失败: {e}")
        return None, None, None


def clear_saved_states():
    """清除所有保存的状态文件"""
    if WORKFLOW_STATE_DIR.exists():
        for f in WORKFLOW_STATE_DIR.glob("workflow_state_*.json"):
            f.unlink()
        _log_message("🗑️ 已清除所有保存的状态文件")
