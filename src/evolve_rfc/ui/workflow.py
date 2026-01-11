"""工作流可视化"""
from collections import deque
from typing import Optional
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich.box import ROUNDED

from .console import console


class WorkflowVisualizer:
    """工作流可视化器"""

    def __init__(self):
        self.progress: Optional[Progress] = None
        self.stages = [
            "加载 RFC",
            "并行评审",
            "观点汇总",
            "多轮辩论",
            "共识形成",
            "输出报告",
        ]

    def start(self) -> "WorkflowVisualizer":
        """开始工作流，显示主进度条"""
        self.progress = Progress(
            SpinnerColumn(style="progress"),
            TextColumn("[progress]{task.description}"),
            BarColumn(complete_style="green", finished_style="green"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
        self.progress.start()
        self.main_task = self.progress.add_task("RFC 评审中...", total=len(self.stages))
        return self

    def update_stage(self, stage_idx: int):
        """更新到指定阶段"""
        if self.progress:
            self.progress.update(
                self.main_task,
                description=f"[cyan]{self.stages[stage_idx]}...",
                advance=1,
            )

    def log评审(self, role: str, message: str):
        """记录评审日志"""
        console.log(f"[cyan][{role}][/] {message}")

    def stop(self):
        """停止进度条"""
        if self.progress:
            self.progress.stop()
            self.progress = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


def show_logo():
    """显示 ASCII Logo"""
    console.print(
        Panel(
            Align(
                Text(
                    r"""  _____            _           ____  _____ ____
 | ____|_   _____ | |_   _____|  _ \|  ___/ ___|
 |  _| \ \ / / _ \| \ \ / / _ \ |_) | |_ | |
 | |___ \ V / (_) | |\ V /  __/  _ <|  _|| |___
 |_____| \_/ \___/|_| \_/ \___|_| \_\_|   \____|
""",
                    justify="left",
                    style="bold cyan",
                ),
                align="center",
            ),
            box=ROUNDED,
            style="cyan",
            subtitle="RFC 智能体协同评审系统 | 🤖 AI 协同 | 📊 实时辩论 | 🎯 共识",
            subtitle_align="center",
        )
    )


def show_voting_table(results: list, round_num: int):
    """显示投票结果表格"""
    table = Table(title=f"🗳️ 第 {round_num} 轮投票结果", box=ROUNDED)
    table.add_column("角色", style="cyan", width=15)
    table.add_column("立场", justify="center", width=12)
    table.add_column("核心观点", overflow="fold")

    for r in results:
        vote = r.get("vote", "待投票") or "待投票"
        stance = "👍 赞成" if vote == "赞成" else "👎 反对" if vote == "反对" else "🤔 弃权"
        stance_style = "green" if vote == "赞成" else "red" if vote == "反对" else "yellow"

        content = r.get("content", "")
        lines = content.split("\n")
        core_point = ""
        for line in lines:
            if "论点:" in line:
                core_point = line.replace("论点:", "").strip('" ')
                break
        if not core_point and content:
            core_point = content[:80].replace("\n", " ")

        role_style = {
            "architect": "green",
            "security": "red",
            "cost_control": "magenta",
            "innovator": "blue",
            "clerk": "white",
        }.get(r["role"].lower(), "white")

        table.add_row(
            f"[{role_style}]{r['role']}[/]",
            f"[{stance_style}]{stance}[/]",
            core_point,
        )

    console.print(table)


def show_consensus_progress(vote_result: dict, threshold: float = 0.8):
    """显示共识进度"""
    yes, no, abstain = vote_result["yes"], vote_result["no"], vote_result["abstain"]
    total = yes + no + abstain
    if total == 0:
        return

    yes_rate = yes / total
    progress_bar = "█" * int(yes_rate * 20) + "░" * (20 - int(yes_rate * 20))
    status = "🎉 已达成共识" if yes_rate >= threshold else "🔄 形成中..." if yes_rate >= 0.5 else "⚠️ 分歧较大"
    status_style = "green" if yes_rate >= threshold else "yellow" if yes_rate >= 0.5 else "red"

    console.print(
        f"\n📊 共识进度: [{progress_bar}] {yes_rate:.0%} (需 {threshold:.0%}) [{status_style}]{status}[/]"
    )
    console.print(f"   赞成: {yes} | 反对: {no} | 弃权: {abstain}\n")


def show_final_report(results: list, vote_result: dict, approved: bool):
    """显示最终报告"""
    yes, no, abstain = vote_result["yes"], vote_result["no"], vote_result["abstain"]
    for_votes = [r for r in results if r.get("vote") == "赞成"]
    against_votes = [r for r in results if r.get("vote") == "反对"]

    for_points = []
    against_points = []
    for r in for_votes:
        for line in r.get("content", "").split("\n"):
            if "论点:" in line:
                point = line.replace("论点:", "").strip('" ')
                if point:
                    for_points.append(f"  • {point}")
                break
    for r in against_votes:
        for line in r.get("content", "").split("\n"):
            if "论点:" in line:
                point = line.replace("论点:", "").strip('" ')
                if point:
                    against_points.append(f"  • {point}")
                break

    result_icon = "✅ 通过" if approved else "❌ 否决"
    result_style = "green" if approved else "red"

    report = Panel(
        f"[bold {result_style}]{result_icon}[/]\n\n"
        f"[green]👍 赞成方观点:[/]\n{for_points[0] if for_points else '  无'}\n\n"
        f"[red]👎 反对方观点:[/]\n{against_points[0] if against_points else '  无'}\n\n"
        f"[cyan]投票统计:[/] 赞成 {yes} | 反对 {no} | 弃权 {abstain}",
        title="📝 最终评审报告",
        box=ROUNDED,
    )
    console.print(report)


def show_workflow_header(rfc_title: str, round_num: Optional[int] = None):
    """显示工作流头部"""
    title = f"📋 RFC 评审: {rfc_title}"
    if round_num:
        title += f" | 第 {round_num} 轮"

    console.print(
        Panel(
            Align(title, align="center"),
            style="cyan",
            subtitle="按 Ctrl+C 可请求人类介入",
            subtitle_align="right",
        )
    )


def show_stage_complete(stage_name: str):
    """显示阶段完成"""
    console.print(f"✅ [green]完成:[/] {stage_name}")


def show_loading(message: str):
    """显示加载状态"""
    console.print(f"⏳ {message}")


class StreamingPanel:
    """流式面板 - 在 Panel 中实时更新内容"""

    def __init__(self, role: str, round_num: int):
        self.role = role
        self.round_num = round_num
        self._chunks: list[str] = []
        self._tail_lines: deque[str] = deque()
        self._current_line: str = ""
        self._role_style = self._get_role_style(role)
        self._role_icon = self._get_role_icon(role)
        self._started = False
        self._live: Optional[Live] = None
        self._panel_height: int = 20  # 默认为20，确保始终为有效整数

    def _get_role_style(self, role: str) -> str:
        styles = {
            "architect": "green",
            "security": "red",
            "cost_control": "magenta",
            "innovator": "blue",
            "clerk": "white",
        }
        return styles.get(role.lower(), "white")

    def _get_role_icon(self, role: str) -> str:
        icons = {
            "architect": "🏛️",
            "security": "🔒",
            "cost_control": "💰",
            "innovator": "💡",
            "clerk": "📝",
        }
        return icons.get(role.lower(), "🤖")

    def start(self):
        """开始流式面板"""
        if self._started:
            return
        self._started = True

        # 给 Live 一个安全的固定高度，避免输出超过终端高度导致渲染异常
        # 经验值：预留标题/边框/少量空白行
        term_height = (
            getattr(getattr(console, "size", None), "height", None) or 40
            if getattr(console, "size", None)
            else 40
        )
        self._panel_height = max(10, min(30, (term_height or 40) - 6))
        # tail 行数略小于 panel 高度（边框/标题占行）
        self._tail_lines = deque(maxlen=max(5, self._panel_height - 4))

        # Live 会接管渲染刷新；避免再用 end="" 直接输出 chunk
        self._live = Live(
            self._make_panel(vote=None),
            console=console,
            refresh_per_second=12,
            transient=True,
            vertical_overflow="crop",
        )
        self._live.start()

    def add_content(self, chunk: str):
        """添加内容片段"""
        if not self._started:
            self.start()

        if not chunk:
            return

        self._chunks.append(chunk)

        # 逐行维护 tail，确保 Live 区域稳定
        self._current_line += chunk
        while "\n" in self._current_line:
            line, rest = self._current_line.split("\n", 1)
            self._tail_lines.append(line)
            self._current_line = rest

        if self._live is not None:
            self._live.update(self._make_panel(vote=None))

    def finish(self, vote: Optional[str] = None):
        """结束流式面板"""
        if not self._started:
            return

        if self._live is not None:
            # 更新最后一次标题（含投票信息），然后停止 Live 以固定最终输出
            self._live.update(self._make_panel(vote=vote))
            self._live.stop()
            self._live = None

        # 结束时把完整内容输出到滚动区，确保“全过程可见”
        full_text = Text("".join(self._chunks), style="white")
        console.print(
            self._make_panel(vote=vote, content=full_text, fixed_height=False)
        )

    def _make_panel(
        self,
        vote: Optional[str],
        content: Optional[Text] = None,
        fixed_height: bool = True,
    ) -> Panel:
        vote_text = vote or "待投票"
        vote_icon = (
            "👍"
            if vote == "赞成"
            else "👎"
            if vote == "反对"
            else "🤔"
            if vote
            else "⏳"
        )
        header = (
            f"{self._role_icon} [{self._role_style}]{self.role}[/]"
            f" | 第 {self.round_num} 轮 | {vote_icon} {vote_text}"
        )

        if content is None:
            # Live 阶段：只展示 tail + 当前行（避免撑爆终端）
            lines = list(self._tail_lines)
            if self._current_line:
                lines.append(self._current_line)
            content = Text("\n".join(lines), style="white")

        return Panel(
            content,
            title=header,
            box=ROUNDED,
            style=self._role_style,
            height=self._panel_height if fixed_height else None,
        )


def stream_ai_output(role: str, chunk: str):
    """流式输出 AI 内容（打字机效果）

    Args:
        role: 角色名称
        chunk: 内容片段
    """
    # 使用 end="" 避免自动换行，实现打字机效果
    if chunk:
        console.print(chunk, end="")


def start_ai_review_header(role: str, round_num: int):
    """显示 AI 开始评审的头部信息"""
    role_styles = {
        "architect": "green",
        "security": "red",
        "cost_control": "magenta",
        "innovator": "blue",
        "clerk": "white",
    }
    role_icons = {
        "architect": "🏛️",
        "security": "🔒",
        "cost_control": "💰",
        "innovator": "💡",
        "clerk": "📝",
    }
    style = role_styles.get(role.lower(), "white")
    icon = role_icons.get(role.lower(), "🤖")

    # 换行后显示头部
    console.print(f"\n{icon} [{style}]{role}[/] 正在评审（第 {round_num} 轮）...")
    console.print("─" * 60, style="dim")


class TokenMonitor:
    """Token 使用量监控器 - 在侧边面板实时显示"""

    def __init__(self):
        self._role_stats: dict[str, dict] = {}  # 角色名 -> 统计数据
        self._total_stats: dict = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        self._live: Optional[Live] = None
        self._started = False

    def update(self, token_data: dict):
        """更新 token 统计数据

        Args:
            token_data: 包含 role, input_tokens, output_tokens, total_tokens, remaining, max_tokens, usage_percent
        """
        role = token_data.get("role", "unknown")
        self._role_stats[role] = {
            "input": token_data.get("input_tokens", 0),
            "output": token_data.get("output_tokens", 0),
            "total": token_data.get("total_tokens", 0),
            "remaining": token_data.get("remaining", 0),
            "max": token_data.get("max_tokens", 128000),
            "percent": token_data.get("usage_percent", 0),
        }

        # 更新总计
        self._total_stats["input_tokens"] = sum(s["input"] for s in self._role_stats.values())
        self._total_stats["output_tokens"] = sum(s["output"] for s in self._role_stats.values())
        self._total_stats["total_tokens"] = sum(s["total"] for s in self._role_stats.values())

        # 如果 Live 已启动，更新显示
        if self._live is not None:
            self._live.update(self._make_panel())

    def start(self):
        """开始监控面板"""
        if self._started:
            return
        self._started = True

        self._live = Live(
            self._make_panel(),
            console=console,
            refresh_per_second=4,  # 较低刷新率，避免过于频繁
            transient=True,
        )
        self._live.start()

    def stop(self):
        """停止监控面板"""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _make_panel(self) -> Panel:
        """创建监控面板"""
        lines = ["[bold cyan]📊 Token 使用监控[/]", ""]

        # 各角色统计
        role_icons = {
            "architect": "🏛️",
            "security": "🔒",
            "cost_control": "💰",
            "innovator": "💡",
            "clerk": "📝",
        }

        for role, stats in self._role_stats.items():
            icon = role_icons.get(role, "🤖")
            percent = stats["percent"]
            bar_len = int(percent / 5)  # 20个字符的进度条
            bar = "█" * bar_len + "░" * (20 - bar_len)

            # 颜色根据使用量变化
            if percent > 80:
                color = "red"
            elif percent > 60:
                color = "yellow"
            else:
                color = "green"

            lines.append(f"{icon} [bold]{role}[/]")
            lines.append(f"  输入: {stats['input']:,} | 输出: {stats['output']:,}")
            lines.append(f"  消耗: {stats['total']:,} / {stats['max']:,}")
            lines.append(f"  [{color}]{bar}[/] {percent:.1f}%")
            lines.append(f"  剩余: [green]{stats['remaining']:,}[/]")
            lines.append("")  # 空行分隔

        # 总计
        total_in = self._total_stats["input_tokens"]
        total_out = self._total_stats["output_tokens"]
        total = total_in + total_out

        lines.append("[bold yellow]═══════════════════════[/]")
        lines.append("[bold]📈 本轮总计[/]")
        lines.append(f"  输入: [cyan]{total_in:,}[/]")
        lines.append(f"  输出: [cyan]{total_out:,}[/]")
        lines.append(f"  合计: [bold cyan]{total:,}[/]")

        content = Text("\n".join(lines), style="white")

        return Panel(
            content,
            title="🔢 Token 监控",
            box=ROUNDED,
            style="cyan",
            width=40,
        )

    def get_summary(self) -> dict:
        """获取统计摘要"""
        return {
            "role_stats": self._role_stats.copy(),
            "total": self._total_stats.copy(),
        }
