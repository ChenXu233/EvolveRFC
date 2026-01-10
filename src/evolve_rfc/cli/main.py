"""EvolveRFC 交互式 CLI

支持键盘上下键、鼠标点击的交互式菜单。
"""
import sys
import time
from pathlib import Path

import questionary
from questionary import Style

from evolve_rfc.ui import (
    show_logo,
    show_ai_review,
    show_voting_table,
    show_consensus_progress,
    show_final_report,
    show_error,
)
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


def run_workflow():
    """运行 RFC 评审工作流"""
    rfc_path = questionary.text(
        "RFC 文件路径",
        default="rfcs/example.md",
        style=custom_style,
    ).ask()

    if not rfc_path or not Path(rfc_path).exists():
        show_error("RFC 文件不存在")
        return

    with open(rfc_path, "r", encoding="utf-8") as f:
        rfc_content = f.read()

    print(f"\n📄 已加载: {rfc_path}\n")

    settings = get_settings()
    max_rounds = settings.workflow.routing.max_rounds
    yes_votes_needed = settings.nightly.creative_proposal.yes_votes_needed
    no_votes_limit = settings.nightly.creative_proposal.no_votes_limit

    print(f"🚀 开始 RFC 评审 (最多 {max_rounds} 轮)\n")

    all_results = []

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'=' * 60}")
        print(f"📍 第 {round_num} 轮评审")
        print(f"{'=' * 60}\n")

        print("⏳ AI 角色正在评审...\n")

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

        print("⏳ 准备下一轮辩论...")
        time.sleep(1)

    vote_result = analyze_votes(all_results)
    show_final_report(all_results, vote_result, approved=False)


def run_nightly():
    """运行夜间守护进程"""
    print("\n🌙 启动夜间守护进程...\n")
    print("未完成，敬请期待！\n")
    raise NotImplementedError("夜间守护进程功能尚未实现")


def show_config():
    """显示配置"""
    settings = get_settings()

    choices = [
        "📊 工作流配置 (轮次、投票阈值)",
        "🤖 角色配置 (启用/禁用角色)",
        "🔙 返回主菜单",
    ]

    while True:
        choice = questionary.select(
            "配置管理",
            choices=choices,
            style=custom_style,
            default="🔙 返回主菜单",
        ).ask()

        if choice == "🔙 返回主菜单" or choice is None:
            break
        elif choice == "📊 工作流配置":
            print("\n📊 当前工作流配置:")
            print(f"   最大轮次: {settings.workflow.routing.max_rounds}")
            print(f"   共识阈值: {settings.workflow.thresholds.consensus_quorum:.0%}")
            print(
                f"   赞成票需求: {settings.nightly.creative_proposal.yes_votes_needed}"
            )
            print(f"   反对票上限: {settings.nightly.creative_proposal.no_votes_limit}")
            print("\n💡 修改配置请编辑 config/workflow.yaml")
        elif choice == "🤖 角色配置":
            print("\n🤖 当前启用的角色:")
            for name, role in settings.workflow.roles.items():
                status = "✅" if role.enabled else "❌"
                vote = "投票" if role.can_vote else "不投票"
                print(f"   {status} {name} ({vote})")
            print("\n💡 修改配置请编辑 config/workflow.yaml")


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
            default="❌ 退出",
        ).ask()

        if choice == "🚀 开始 RFC 评审工作流" or choice is None:
            run_workflow()
        elif choice == "🌙 启动夜间守护进程":
            run_nightly()
        elif choice == "⚙️  配置管理":
            show_config()
        elif choice == "❌ 退出":
            print("\n👋 再见！\n")
            sys.exit(0)


def main():
    """主入口"""
    show_logo()
    print()
    main_menu()


if __name__ == "__main__":
    main()
