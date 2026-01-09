"""工作流入口点"""

from evolve_rfc.workflow.graph import build_workflow_graph

if __name__ == "__main__":
    import sys

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
            rfc_content = """# 示例RFC

## 问题描述
这是一个测试RFC文档。

## 提议方案
请评审这个RFC的设计。

## 预期影响
请评估影响范围。
"""

    # 构建并运行工作流
    app = build_workflow_graph()
    print("🚀 启动RFC评审工作流...")
    print("=" * 50)

    # 编译为可运行应用
    final_state = app.invoke({"rfc_content": rfc_content})

    print("=" * 50)
    print("✅ 工作流执行完成")
    print(f"最终状态: {final_state.get('workflow_status', '未知')}")
