"""面板显示组件"""
from typing import Optional
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED
from .console import console


def show_welcome():
    """显示欢迎界面"""
    console.print(
        Panel(
            Text(
                "EvolveRFC\n"
                "RFC 智能体协同评审系统\n\n"
                "🎯 模拟技术议会，多视角协同评审\n"
                "🔄 动态共识形成，多轮辩论投票\n"
                "🤖 AI 自主运作，人类最终决策",
                justify="center",
                style="bold cyan",
            ),
            title="🚀 欢迎使用",
            box=ROUNDED,
            style="cyan",
        )
    )


def show_role_status(roles: list, current_round: int = 1):
    """显示角色状态面板"""
    table = Table(title=f"👥 评审角色 (第 {current_round} 轮)", box=ROUNDED)
    table.add_column("角色", style="cyan")
    table.add_column("状态", justify="center")
    table.add_column("投票", justify="center")
    table.add_column("观点", overflow="fold")

    for role in roles:
        # 状态图标
        if role.get("done"):
            status = "✅ 完成"
        elif role.get("speaking"):
            status = "💬 发言中"
        else:
            status = "⏳ 等待"

        # 投票图标
        vote = role.get("vote", "")
        if vote == "for":
            vote_icon = "👍 赞成"
        elif vote == "against":
            vote_icon = "👎 反对"
        elif vote == "abstain":
            vote_icon = "🤔 弃权"
        else:
            vote_icon = "-"

        # 观点预览
        viewpoint = role.get("viewpoint", "")
        if len(viewpoint) > 50:
            viewpoint = viewpoint[:47] + "..."

        role_style = role.get("style", "white")
        table.add_row(
            f"[{role_style}]{role['name']}[/]",
            status,
            vote_icon,
            viewpoint,
        )

    console.print(table)


def show_voting_results(votes: dict, total: int):
    """显示投票结果"""
    table = Table(title="🗳️ 投票结果", box=ROUNDED)
    table.add_column("角色", style="cyan")
    table.add_column("投票", justify="center")
    table.add_column("观点", overflow="fold")

    for role_name, vote_data in votes.items():
        if vote_data.get("vote") == "for":
            vote_icon = "👍 赞成"
            vote_style = "green"
        elif vote_data.get("vote") == "against":
            vote_icon = "👎 反对"
            vote_style = "red"
        else:
            vote_icon = "🤔 弃权"
            vote_style = "yellow"

        viewpoint = vote_data.get("reasoning", "")
        if len(viewpoint) > 80:
            viewpoint = viewpoint[:77] + "..."

        table.add_row(
            f"[cyan]{role_name}[/]",
            f"[{vote_style}]{vote_icon}[/]",
            viewpoint,
        )

    console.print(table)

    # 统计
    for_count = sum(1 for v in votes.values() if v.get("vote") == "for")
    against_count = sum(1 for v in votes.values() if v.get("vote") == "against")
    abstain_count = sum(1 for v in votes.values() if v.get("vote") == "abstain")

    console.print(
        f"📊 统计: 赞成 {for_count} | 反对 {against_count} | 弃权 {abstain_count} / {total}"
    )


def show_consensus(consensus_score: float, quorum: float = 0.8):
    """显示共识达成状态"""
    if consensus_score >= quorum:
        console.print(
            f"🎉 [green]共识已达成![/] (达成率: {consensus_score:.0%} ≥ {quorum:.0%})"
        )
    elif consensus_score >= 0.5:
        console.print(
            f"⚠️ [yellow]接近共识[/] (达成率: {consensus_score:.0%}, 需 {quorum:.0%})"
        )
    else:
        console.print(
            f"❌ [red]尚未达成共识[/] (达成率: {consensus_score:.0%}, 需 {quorum:.0%})"
        )


def show_deadlock(issues: list):
    """显示僵局状态"""
    if issues:
        console.print(Panel(f"⚠️ 僵局! 以下问题未解决:\n\n" + "\n".join(f"- {i}" for i in issues)))
    else:
        console.print("✅ 所有问题已解决")


def show_final_report(
    title: str,
    summary: str,
    consensus: str,
    issues: list,
    actions: list,
):
    """显示最终报告"""
    issues_text = "\n".join(f"- [red]❌[/] {i}" for i in issues) if issues else "- 无"
    actions_text = "\n".join(f"- [green]→[/] {a}" for a in actions) if actions else "- 无"

    report = Panel(
        f"[bold cyan]{title}[/]\n\n"
        f"[yellow]摘要:[/]\n{summary}\n\n"
        f"[yellow]共识:[/]\n{consensus}\n\n"
        f"[yellow]待解决问题:[/]\n{issues_text}\n\n"
        f"[yellow]建议行动:[/]\n{actions_text}",
        title="📝 最终报告",
        box=ROUNDED,
    )
    console.print(report)


def show_error(message: str):
    """显示错误信息"""
    console.print(Panel(f"❌ [red]错误[/]\n\n{message}", title="💥 出错了"))


def show_warning(message: str):
    """显示警告信息"""
    console.print(f"⚠️ [yellow]警告:[/] {message}")


def show_stage_complete(stage_name: str):
    """显示阶段完成"""
    console.print(f"✅ [green]完成:[/] {stage_name}")
