"""工作流入口点"""
import sys

from evolve_rfc.workflow.graph import build_workflow_graph
from evolve_rfc.core.state import create_initial_state
from evolve_rfc.mcp.main import ensure_mcp_started
from evolve_rfc.ui import (
    show_welcome,
    WorkflowVisualizer,
    show_workflow_header,
    show_stage_complete,
    show_error,
)

if __name__ == "__main__":
    # 自动启动 MCP Server（让 AI 可以调用工具）
    ensure_mcp_started()

    # 显示欢迎界面
    show_welcome()

    # 获取 RFC 内容（从文件或命令行参数）
    if len(sys.argv) > 1:
        rfc_path = sys.argv[1]
        with open(rfc_path, "r", encoding="utf-8") as f:
            rfc_content = f.read()
    else:
        default_rfc = "rfcs/example.md"
        try:
            with open(default_rfc, "r", encoding="utf-8") as f:
                rfc_content = f.read()
        except FileNotFoundError:
            show_error("请提供 RFC 文件路径作为参数，或确保 rfcs/example.md 存在。")
            sys.exit(1)

    # 构建并运行工作流
    with WorkflowVisualizer() as viz:
        # 显示工作流头部
        show_workflow_header("RFC 评审")

        viz.update_stage(0)  # 加载 RFC

        # 构建工作流
        app = build_workflow_graph()

        viz.update_stage(1)  # 并行评审

        # 编译为可运行应用
        initial_state = create_initial_state(rfc_content)

        # 执行工作流
        final_state = app.invoke(initial_state)

        viz.update_stage(2)  # 观点汇总
        viz.update_stage(3)  # 多轮辩论
        viz.update_stage(4)  # 共识形成
        viz.update_stage(5)  # 输出报告

    # 显示最终结果
    show_stage_complete("RFC 评审完成")
    print()
    print(f"最终状态: {final_state.get('workflow_status', '未知')}")
