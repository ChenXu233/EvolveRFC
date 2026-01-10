"""深度审计模式

分析项目代码，发现设计缺陷、技术债务。
"""

from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
import json

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..settings import get_settings

if TYPE_CHECKING:
    pass


def _create_client():
    """创建 LLM 客户端（使用全局配置）"""
    settings = get_settings()
    llm_config = settings.workflow.llm

    if llm_config.provider == "openai":
        return ChatOpenAI(
            model=llm_config.model,
            temperature=llm_config.temperature,
            base_url=llm_config.base_url,
        )
    elif llm_config.provider == "anthropic":
        return ChatAnthropic(
            model_name=llm_config.model,
            temperature=llm_config.temperature,
            base_url=llm_config.base_url,
            timeout=llm_config.timeout,
            stop=llm_config.stop,
        )
    else:
        raise ValueError(f"不支持的 provider: {llm_config.provider}")


def run_audit_mode(config: Dict[str, Any], output_dir: str):
    """运行深度审计模式"""
    print("🔍 进入深度审计模式...")

    # 加载配置
    settings = get_settings()
    audit_config = settings.nightly.code_analysis
    scope = audit_config.scope
    focus_dirs = audit_config.focus_dirs

    # 获取代码
    code_files = _collect_code_files(focus_dirs)
    print(f"📁 收集到 {len(code_files)} 个代码文件")

    if not code_files:
        print("📭 无代码文件可分析，退出")
        return

    # 分析代码
    client = _create_client()
    issues = _analyze_code(client, code_files, scope, audit_config)

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


def _analyze_code(client, files: list, scope: str, audit_config) -> list:
    """分析代码"""
    issues = []

    # 简化实现：分析前 max_files_analyze 个文件
    files_to_analyze = files[:audit_config.max_files_analyze]
    for file_path in files_to_analyze:
        try:
            content = Path(file_path).read_text(encoding="utf-8")[:3000]
            response = client.invoke([
                SystemMessage(content=audit_config.system_prompt),
                HumanMessage(content=audit_config.user_prompt_template.format(
                    file_path=file_path,
                    file_content=content
                )),
            ])
            response_text = response.content

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
