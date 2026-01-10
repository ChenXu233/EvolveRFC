"""工作流可视化"""
from typing import Optional
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
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
                    "███████╗███╗   ███╗ █████╗ ██╗     ██╗     ███████╗██╗  ██╗\n"
                    "██╔════╝████╗  ████║██╔══██╗██║     ██║     ██╔════╝╚██╗██╔╝\n"
                    "████╗  ██╔██╗ ██╔██║███████║██║     ██║     █████╗   ╚███╔╝ \n"
                    "██╔══╝  ██║╚██╗██║██╔══██║██║     ██║     ██╔══╝   ██╔██╗ \n"
                    "███████╗██║ ╚████║██║  ██║███████╗███████╗███████╗██╔╝ ██╗\n"
                    "╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝",
                    justify="center",
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


def show_ai_review(role: str, content: str, vote: str, round_num: int):
    """显示 AI 角色评审"""
    role_icons = {
        "architect": "🏛️",
        "security": "🔒",
        "cost_control": "💰",
        "innovator": "💡",
        "clerk": "📝",
    }
    role_styles = {
        "architect": "green",
        "security": "red",
        "cost_control": "magenta",
        "innovator": "blue",
        "clerk": "white",
    }

    icon = role_icons.get(role.lower(), "🤖")
    style = role_styles.get(role.lower(), "white")
    vote_icon = "👍" if vote == "赞成" else "👎" if vote == "反对" else "🤔"

    header = f"{icon} [{style}]{role}[/] {vote_icon} {vote}"
    content_preview = content[:600] if len(content) > 600 else content

    console.print(
        Panel(
            Text(content_preview, style="white"),
            title=header,
            box=ROUNDED,
            style=style,
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
