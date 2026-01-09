"""深度审计模式

分析项目代码，发现设计缺陷、技术债务。
"""

from pathlib import Path
from typing import Dict, Any
import json
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


def _create_client() -> ChatOpenAI:
    """创建LLM客户端"""
    api_key = os.getenv("MINIMAX_API_KEY")
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY 未设置")
    return ChatOpenAI(
        model="minimax-m2.1",
        api_key=api_key,
        base_url=base_url,
    )


def run_audit_mode(config: Dict[str, Any], output_dir: str):
    """运行深度审计模式"""
    print("🔍 进入深度审计模式...")

    # 加载配置
    audit_config = config.get("nightly", {}).get("code_analysis", {})
    scope = audit_config.get("scope", "diff")
    focus_dirs = audit_config.get("focus_dirs", ["src"])

    # 获取代码
    code_files = _collect_code_files(focus_dirs)
    print(f"📁 收集到 {len(code_files)} 个代码文件")

    if not code_files:
        print("📭 无代码文件可分析，退出")
        return

    # 分析代码
    client = _create_client()
    issues = _analyze_code(client, code_files, scope)

    # 生成报告
    if issues:
        report = _generate_report(issues, code_files)
        _save_output(output_dir, "audit_report.md", report)
        print(f"✅ 发现 {len(issues)} 个问题，已生成报告")
    else:
        print("✅ 未发现问题，静默结束")


def _collect_code_files(dirs: list) -> list:
    """收集代码文件"""
    code_files = []
    for dir_path in dirs:
        path = Path(dir_path)
        if path.exists():
            for ext in ["*.py", "*.ts", "*.js", "*.go", "*.rs"]:
                code_files.extend(path.rglob(ext))
    return [str(f) for f in code_files[:50]]  # 限制数量


def _analyze_code(client: ChatOpenAI, files: list, scope: str) -> list:
    """分析代码"""
    issues = []

    # 构建提示词
    prompt = f"""你是一个苛刻的代码审查员。分析以下代码，目标是找出：
1. 设计反模式（单点故障、紧耦合、过度复杂、违反SOLID）
2. 潜在缺陷（资源泄漏、并发问题、安全漏洞、未处理边界）
3. 技术债务（重复代码、硬编码、魔法数字、缺失注释/测试）

请输出JSON格式：
{{
  "问题列表": [
    {{
      "文件": "路径",
      "行号": 行号,
      "描述": "问题描述",
      "严重性": "高|中|低",
      "改进建议": "一句话建议"
    }}
  ]
}}

分析范围：{"最新Diff" if scope == "diff" else "全量代码"}
"""

    # 简化实现：分析前10个文件
    for file_path in files[:10]:
        try:
            content = Path(file_path).read_text(encoding="utf-8")[:3000]
            response = client.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=f"文件: {file_path}\n\n{content}"),
            ])
            response_text = response.content if hasattr(response, 'content') else str(response)

            # 解析结果
            result = _parse_response(response_text)
            if result:
                issues.extend(result)

        except Exception as e:
            print(f"⚠️ 分析失败: {file_path}: {e}")

    return issues


def _parse_response(response: str) -> list:
    """解析LLM响应"""
    try:
        # 尝试提取JSON
        if "{" in response and "}" in response:
            start = response.find("{")
            end = response.rfind("}") + 1
            json_str = response[start:end]
            data = json.loads(json_str)
            return data.get("问题列表", [])
    except Exception:
        pass
    return []


def _generate_report(issues: list, files: list) -> str:
    """生成审计报告"""
    # 按严重性排序
    高 = [i for i in issues if i.get("严重性") == "高"]
    中 = [i for i in issues if i.get("严重性") == "中"]
    低 = [i for i in issues if i.get("严重性") == "低"]

    report = f"""# 代码审计报告

## 概述

- 分析文件数：{len(files)}
- 发现问题总数：{len(issues)}
  - 高严重性：{len(高)} 个
  - 中严重性：{len(中)} 个
  - 低严重性：{len(低)} 个

## 高严重性问题

"""

    for issue in 高:
        report += f"""### {issue.get('文件', '未知')}:{issue.get('行号', 'N/A')}

- **描述**: {issue.get('描述', '')}
- **建议**: {issue.get('改进建议', '')}

"""

    report += """
## 中严重性问题

"""
    for issue in 中[:10]:  # 限制数量
        report += f"- {issue.get('文件', '')}:{issue.get('行号', '')} - {issue.get('描述', '')}\n"

    report += """
## 低严重性问题（略）

---

*由 EvolveRFC 夜间守护进程自动生成*
"""

    return report


def _save_output(output_dir: str, filename: str, content: str):
    """保存输出文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(output_dir) / filename
    output_path.write_text(content, encoding="utf-8")
