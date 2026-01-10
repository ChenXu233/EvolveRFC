"""工作流入口点"""

from evolve_rfc.workflow.graph import build_workflow_graph
from evolve_rfc.core.state import create_initial_state
from evolve_rfc.mcp.main import ensure_mcp_started

if __name__ == "__main__":
    import sys

    # 自动启动 MCP Server（让 AI 可以调用工具）
    ensure_mcp_started()

    # 获取RFC内容（从文件或命令行参数）
    if len(sys.argv) > 1:
        rfc_path = sys.argv[1]
        with open(rfc_path, "r", encoding="utf-8") as f:
            rfc_content = f.read()
    else:
        # 默认使用 rfcs 目录下的示例
        default_rfc = "rfcs/example.md"
        try:
            with open(default_rfc, "r", encoding="utf-8") as f:
                rfc_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                "请提供RFC文件路径作为参数，或确保 rfcs/example.md 存在。"
            )

    # 构建并运行工作流
    app = build_workflow_graph()
    print("🚀 启动RFC评审工作流...")
    print("=" * 50)

    # 编译为可运行应用
    initial_state = create_initial_state(rfc_content)
    final_state = app.invoke(initial_state)

    print("=" * 50)
    print("✅ 工作流执行完成")
    print(f"最终状态: {final_state.get('workflow_status', '未知')}")
