"""数据面板组件

提供可复用的 Textual 面板组件：
- RoleStatusPanel: 角色状态面板
- VotingResultPanel: 投票结果面板
- TokenDataPanel: Token 统计面板
- WorkflowStatusPanel: 工作流状态面板
"""

from typing import Dict, List, Any
from textual.containers import Vertical
from textual.widgets import Label, DataTable, Static


class RoleStatusPanel(Vertical):
    """显示角色状态"""

    CSS = """
    RoleStatusPanel {
        height: auto;
    }
    """

    def compose(self):
        yield Label("👥 评审角色状态", classes="panel-title")
        yield DataTable(id="role_table", cursor_type="row")

    def on_mount(self):
        table = self.query_one("#role_table", DataTable)
        table.add_columns("角色", "状态", "投票", "观点摘要")

    def update_roles(self, roles_data: List[Dict]):
        table = self.query_one("#role_table", DataTable)
        table.clear()
        for role in roles_data:
            name = role.get("name", "Unknown")
            # 状态
            if role.get("done"):
                status = "✅ 完成"
            elif role.get("speaking"):
                status = "💬 发言中"
            else:
                status = "⏳ 等待"

            # 投票
            vote = role.get("vote", "")
            icon = "-"
            if vote == "for":
                icon = "👍"
            elif vote == "against":
                icon = "👎"
            elif vote == "abstain":
                icon = "🤔"

            # 观点
            viewpoint = str(role.get("viewpoint", ""))
            if len(viewpoint) > 30:
                viewpoint = viewpoint[:27] + "..."

            table.add_row(name, status, icon, viewpoint)


class VotingResultPanel(Vertical):
    """显示投票统计"""

    CSS = """
    VotingResultPanel {
        height: auto;
    }
    """

    def compose(self):
        yield Label("🗳️ 投票结果", classes="panel-title")
        yield Static("暂无投票数据", id="voting_summary", classes="panel-content")
        yield DataTable(id="voting_table")

    def on_mount(self):
        table = self.query_one("#voting_table", DataTable)
        table.add_columns("角色", "投票", "理由")

    def update_results(self, votes: Dict, total: int):
        table = self.query_one("#voting_table", DataTable)
        table.clear()

        for_count = 0
        against_count = 0
        abstain_count = 0

        # 如果 votes 是 role -> data 的字典
        if isinstance(votes, dict) and "yes" not in votes:
            for role, data in votes.items():
                vote = data.get("vote")
                if vote == "for":
                    for_count += 1
                    icon = "👍"
                elif vote == "against":
                    against_count += 1
                    icon = "👎"
                else:
                    abstain_count += 1
                    icon = "🤔"

                reason = data.get("reasoning", "")
                if len(reason) > 50:
                    reason = reason[:47] + "..."

                table.add_row(role, icon, reason)
        # 如果 votes 是摘要字典 (analyze_votes 返回值)
        elif isinstance(votes, dict) and "yes" in votes:
            for_count = votes.get("yes", 0)
            against_count = votes.get("no", 0)
            abstain_count = votes.get("abstain", 0)

        summary = f"赞成: [green]{for_count}[/] | 反对: [red]{against_count}[/] | 弃权: [yellow]{abstain_count}[/] / {total}"
        self.query_one("#voting_summary", Static).update(summary)


class TokenDataPanel(Vertical):
    """Token 消耗统计"""

    CSS = """
    TokenDataPanel {
        height: auto;
    }
    """

    def compose(self):
        yield Label("📊 Token 统计", classes="panel-title")
        yield DataTable(id="token_table")

    def on_mount(self):
        table = self.query_one("#token_table", DataTable)
        table.add_columns("角色", "输入", "输出", "合计", "%")

    def update_tokens(self, stats_map: Dict[str, Any]):
        table = self.query_one("#token_table", DataTable)
        table.clear()
        for role, stats in sorted(stats_map.items()):
            # 支持字典格式（来自 update_tokens 调用）和对象格式
            if isinstance(stats, dict):
                input_tokens = stats.get("input_tokens", 0)
                output_tokens = stats.get("output_tokens", 0)
                total_tokens = stats.get("total_tokens", 0)
                usage_percent = stats.get("usage_percent", 0.0)
            else:
                # 对象格式（如 TokenStats）
                input_tokens = getattr(stats, 'input_tokens', 0)
                output_tokens = getattr(stats, 'output_tokens', 0)
                total_tokens = getattr(stats, 'total_tokens', 0)
                usage_percent = getattr(stats, 'usage_percent', 0.0)
            
            table.add_row(
                str(role),
                f"{input_tokens:,}",
                f"{output_tokens:,}",
                f"{total_tokens:,}",
                f"{usage_percent:.1f}%",
            )


class WorkflowStatusPanel(Vertical):
    """工作流状态面板 - 展示决策层、评审层、服务层的层次结构"""

    CSS = """
    WorkflowStatusPanel {
        height: auto;
    }
    .layer-header {
        background: $accent;
        color: $text;
        padding: 0 1;
        text-style: bold;
        height: auto;
    }
    .divider {
        color: $text-muted;
        height: 1;
    }
    """

    def compose(self):
        yield Label("🔄 工作流状态", classes="panel-title")
        # 轮次显示
        yield Static("第 1 轮 / 最多 10 轮", id="round_display")
        # 工作流阶段显示
        yield Static("📋 等待开始", id="stage_display")
        yield Static("=" * 30, classes="divider")
        # 层次结构可视化
        yield Label("🎯 决策层", classes="layer-header")
        yield Static("👤 人类主席 (待命)", id="human_status")
        yield Static("=" * 30, classes="divider")
        yield Label("👥 评审层", classes="layer-header")
        yield Static("🏛️ 架构师: ⏳ 等待", id="role_architect")
        yield Static("🔒 安全官: ⏳ 等待", id="role_security")
        yield Static("💰 成本控制: ⏳ 等待", id="role_cost")
        yield Static("💡 创新派: ⏳ 等待", id="role_innovator")
        yield Static("=" * 30, classes="divider")
        yield Label("📝 服务层", classes="layer-header")
        yield Static("📋 书记官: ⏳ 等待", id="role_clerk")

    def update_round(self, current: int, max_rounds: int):
        """更新轮次显示"""
        self.query_one("#round_display", Static).update(f"🔄 第 {current} 轮 / 最多 {max_rounds} 轮")

    def update_stage(self, stage: str):
        """更新工作流阶段"""
        stage_map = {
            "init": "📋 初始化...",
            "parallel_review": "💬 并行评审中...",
            "vote_analyzer": "🗳️ 统计投票...",
            "human_oversight": "👤 等待人类决策...",
            "clerk_summary": "📝 书记官汇总...",
            "final_report": "📄 生成最终报告...",
            "completed": "✅ 工作流完成",
        }
        self.query_one("#stage_display", Static).update(stage_map.get(stage, stage))

    def update_role_status(self, role: str, status: str):
        """更新角色状态"""
        role_id_map = {
            "architect": "#role_architect",
            "security": "#role_security",
            "cost_control": "#role_cost",
            "innovator": "#role_innovator",
            "clerk": "#role_clerk",
        }
        role_name_map = {
            "architect": "🏛️ 架构师",
            "security": "🔒 安全官",
            "cost_control": "💰 成本控制",
            "innovator": "💡 创新派",
            "clerk": "📋 书记官",
        }
        status_map = {
            "waiting": "⏳ 等待",
            "speaking": "💬 发言中",
            "completed": "✅ 完成",
            "voting": "🗳️ 投票中",
        }

        role_id = role_id_map.get(role.lower())
        if role_id:
            role_name = role_name_map.get(role.lower(), role)
            status_text = status_map.get(status, status)
            self.query_one(role_id, Static).update(f"{role_name}: {status_text}")

    def update_human_status(self, status: str):
        """更新人类状态"""
        status_map = {
            "waiting": "👤 人类主席 (待命)",
            "intervention": "👤 人类主席 (介入中)",
            "decision": "👤 人类主席 (已决策)",
        }
        self.query_one("#human_status", Static).update(status_map.get(status, status))
