"""EvolveRFC 交互式 CLI

支持键盘上下键、鼠标点击的交互式菜单。
"""
import sys
import time
from pathlib import Path
from typing import Optional

import questionary
from questionary import Style
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.box import ROUNDED
from rich.align import Align

from evolve_rfc.ui.console import console
from evolve_rfc.mcp.main import ensure_mcp_started
from evolve_rfc.shared.debate import run_parallel_review, analyze_votes, check_approval
from evolve_rfc.settings import get_settings


# 自定义主题
custom_style = Style([
    ("pointer", "fg:#00ff00 bold"),
    ("highlighted", "fg:#00ff00 bold"),
    ("selected", "fg:#00ff00"),
    ("header", "fg:#00ffff bold"),
])


def show_logo():
    """显示 Logo"""
    console.print(
        Panel(
            Align(
                Text(
                    "███████╗███╗   ███╗ █████╗ ██╗     ██╗     ███████╗██╗  ██╗\n"
                    "██╔════╝████╗  ████║██╔══██╗██║     ██║     ██╔════╝╚██╗██╔╝\n"
                    "█████╗  ██╔██╗ ██╔██║███████║██║     ██║     █████╗   ╚███╔╝ \n"
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


def run_workflow():
    """运行 RFC 评审工作流"""
    rfc_path = questionary.text(
        "RFC 文件路径",
        default="rfcs/example.md",
        style=custom_style,
    ).ask()

    if not rfc_path or not Path(rfc_path).exists():
        console.print("[red]错误:[/] RFC 文件不存在")
        return

    with open(rfc_path, "r", encoding="utf-8") as f:
        rfc_content = f.read()

    console.print(f"\n📄 已加载: {rfc_path}\n")

    settings = get_settings()
    max_rounds = settings.workflow.routing.max_rounds
    yes_votes_needed = settings.nightly.creative_proposal.yes_votes_needed
    no_votes_limit = settings.nightly.creative_proposal.no_votes_limit

    console.print(f"🚀 开始 RFC 评审 (最多 {max_rounds} 轮)\n")

    all_results = []

    for round_num in range(1, max_rounds + 1):
        console.print(f"\n{'='*60}")
        console.print(f"📍 第 {round_num} 轮评审")
        console.print(f"{'='*60}\n")

        console.print("⏳ AI 角色正在评审...\n")

        results = run_parallel_review(content=rfc_content, current_round=round_num)
        all_results.extend(results)

        for r in results:
            show_ai_review(r["role"], r["content"], r.get("vote") or "弃权", round_num)

        vote_result = analyze_votes(results)
        show_voting_table(results, round_num)
        show_consensus_progress(vote_result)

        check_result = check_approval(
            vote_result=vote_result,
            max_rounds=max_rounds,
            current_round=round_num,
            yes_votes_needed=yes_votes_needed,
            no_votes_limit=no_votes_limit,
        )

        if check_result["finished"]:
            show_final_report(results, vote_result, check_result["approved"])
            return

        console.print("⏳ 准备下一轮辩论...")
        time.sleep(1)

    vote_result = analyze_votes(all_results)
    show_final_report(all_results, vote_result, approved=False)


def run_nightly():
    """运行夜间守护进程"""
    console.print("\n🚀 启动夜间守护进程...\n")
    console.print("💡 提示: 使用以下命令在后台运行")
    console.print("   [cyan]uv run pdm nightly[/]\n")
    console.print("📖 或配置 crontab 定时执行:")
    console.print("   [cyan]0 0 * * * cd /path/to/project && uv run pdm nightly[/]\n")

    if questionary.confirm("是否立即运行一次？", default=False).ask():
        from .daemon import main as nightly_main
        nightly_main()


def show_config():
    """显示/修改配置"""
    settings = get_settings()

    choices = [
        "📊 工作流配置 (轮次、投票阈值)",
        "🔧 LLM 配置 (模型、API密钥)",
        "🤖 角色配置 (启用/禁用角色)",
        "📁 MCP Server 配置",
        "🔙 返回主菜单",
    ]

    while True:
        choice = questionary.select(
            "配置管理",
            choices=choices,
            style=custom_style,
            default=0,
        ).ask()

        if choice == "🔙 返回主菜单" or choice is None:
            break
        elif choice == "📊 工作流配置":
            console.print("\n📊 当前工作流配置:")
            console.print(f"   最大轮次: {settings.workflow.routing.max_rounds}")
            console.print(f"   共识阈值: {settings.workflow.thresholds.consensus_quorum:.0%}")
            console.print(f"   赞成票需求: {settings.nightly.creative_proposal.yes_votes_needed}")
            console.print(f"   反对票上限: {settings.nightly.creative_proposal.no_votes_limit}")
            console.print("\n💡 修改配置请编辑 [cyan]config/workflow.yaml[/]")
        elif choice == "🤖 角色配置":
            console.print("\n🤖 当前启用的角色:")
            for name, role in settings.workflow.roles.items():
                status = "✅" if role.enabled else "❌"
                vote = "投票" if role.can_vote else "不投票"
                console.print(f"   {status} {name} ({vote})")
            console.print("\n💡 修改配置请编辑 [cyan]config/workflow.yaml[/]")
        elif choice.startswith("🔧") or choice.startswith("📁"):
            console.print(f"\n💡 配置路径: [cyan]config/[/] 目录下的 YAML 文件")


def main_menu():
    """主菜单"""
    while True:
        choices = [
            "🚀 开始 RFC 评审工作流",
            "🌙 启动夜间守护进程",
            "⚙️  配置管理",
            "❌ 退出",
        ]

        choice = questionary.select(
            "请选择操作",
            choices=choices,
            style=custom_style,
            default=0,
        ).ask()

        if choice == "🚀 开始 RFC 评审工作流" or choice is None:
            run_workflow()
        elif choice == "🌙 启动夜间守护进程":
            run_nightly()
        elif choice == "⚙️  配置管理":
            show_config()
        elif choice == "❌ 退出":
            console.print("\n👋 再见！\n")
            sys.exit(0)


def main():
    """主入口"""
    show_logo()
    console.print()
    main_menu()


if __name__ == "__main__":
    main()
