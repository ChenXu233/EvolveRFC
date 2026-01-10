"""RFC预讨论模式

对已存在的RFC草案进行预讨论，生成预审意见。
"""

from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
from datetime import datetime

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


def run_discuss_mode(config: Dict[str, Any], output_dir: str):
    """运行RFC预讨论模式"""
    print("💬 进入现有RFC预讨论模式...")

    # 加载配置
    settings = get_settings()
    discuss_config = settings.nightly.rfc_pre_discussion
    max_rfcs = discuss_config.max_rfcs_per_night

    # 收集待评审RFC
    rfc_files = _collect_pending_rfcs()
    print(f"📁 找到 {len(rfc_files)} 个待评审RFC")

    if not rfc_files:
        print("📭 无待评审RFC，静默结束")
        return

    # 限制数量
    rfc_files = rfc_files[:max_rfcs]

    # 并行预讨论
    client = _create_client()
    results = []

    for rfc_path in rfc_files:
        try:
            result = _pre_discuss_rfc(client, rfc_path, discuss_config)
            if result:
                results.append(result)
        except Exception as e:
            print(f"⚠️ 预讨论失败: {rfc_path}: {e}")

    # 生成汇总报告
    if results:
        report = _generate_summary_report(results)
        _save_output(output_dir, "rfc_pre_discussion_summary.md", report)
        print(f"✅ 完成 {len(results)} 个RFC预讨论，已生成汇总报告")
    else:
        print("📭 无有效预审结果，静默结束")


def _collect_pending_rfcs() -> list:
    """收集待评审RFC"""
    rfc_dir = Path("rfcs")
    if not rfc_dir.exists():
        return []

    # 查找所有.md文件
    rfc_files = list(rfc_dir.glob("*.md"))

    # 过滤掉已完成的（可以根据文件名或内容判断）
    pending = []
    for rfc_path in rfc_files:
        content = rfc_path.read_text(encoding="utf-8")
        # 简单判断：包含 "status: draft" 或 "待评审"
        if "draft" in content.lower() or "待评审" in content:
            pending.append(rfc_path)

    return sorted(pending, key=lambda p: p.stat().st_mtime, reverse=True)


def _pre_discuss_rfc(client, rfc_path: Path, discuss_config) -> dict:
    """对单个RFC进行预讨论"""
    content = rfc_path.read_text(encoding="utf-8")[:5000]

    response = client.invoke([
        SystemMessage(content=discuss_config.system_prompt),
        HumanMessage(content=discuss_config.user_prompt_template.format(
            rfc_path=rfc_path.name,
            rfc_content=content
        )),
    ])
    response_text = response.content

    # 解析结果
    result = _parse_response(response_text, rfc_path.name)
    result["rfc_path"] = str(rfc_path)
    return result


def _parse_response(response: str, filename: str) -> dict:
    """解析响应"""
    result = {
        "rfc_id": filename.replace(".md", ""),
        "rfc_title": filename.replace(".md", ""),
        "预审摘要": {
            "核心观点": "待解析",
            "优点": [],
            "风险点": [],
            "建议修改": [],
        },
        "投票结果": {"赞成": 0, "反对": 0, "弃权": 0},
    }

    # 简单解析
    if "核心观点" in response:
        result["预审摘要"]["核心观点"] = response.split("核心观点:")[1].split("\n")[0].strip().strip('"')

    return result


def _generate_summary_report(results: list) -> str:
    """生成汇总报告"""
    report = f"""# RFC预审汇总报告

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 概览

- 预审RFC数量：{len(results)}

"""

    for result in results:
        report += f"""### {result['rfc_id']}

**核心观点**: {result['预审摘要']['核心观点']}

**投票结果**: 赞成{result['投票结果']['赞成']} / 反对{result['投票结果']['反对']} / 弃权{result['投票结果']['弃权']}

---
"""

    report += """
*由 EvolveRFC 夜间守护进程自动生成*
"""

    return report


def _save_output(output_dir: str, filename: str, content: str):
    """保存输出文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(output_dir) / filename
    output_path.write_text(content, encoding="utf-8")
