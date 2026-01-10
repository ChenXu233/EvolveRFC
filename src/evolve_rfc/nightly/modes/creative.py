"""创新提案模式

基于审计结果或自由发散，提出新RFC想法（需多轮智能体审核）。
"""

from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ...settings import get_settings
from ...shared import run_parallel_review, analyze_votes, check_approval

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


def run_creative_mode(config: Dict[str, Any], output_dir: str):
    """运行创新提案模式"""
    print("💡 进入创新提案模式...")

    # 加载配置
    settings = get_settings()
    creative_config = settings.nightly.creative_proposal
    max_rounds = creative_config.max_rounds

    # 生成创新想法
    client = _create_client()
    ideas = _generate_ideas(client, config, creative_config)

    if not ideas:
        print("📭 无创新想法，静默结束")
        return

    # 多轮辩论审核（复用 shared/debate.py）
    approved_proposals = []
    controversial_ideas = []  # 收集未通过的ideas，避免重复辩论
    for idea in ideas:
        result = _multi_round_debate(idea, max_rounds, creative_config)
        if result["approved"]:
            approved_proposals.append(result)
        else:
            controversial_ideas.append(result["idea"])

    # 生成输出
    if approved_proposals:
        report = _generate_proposal_report(approved_proposals)
        _save_output(output_dir, "creative_proposal.md", report)
        print(f"✅ 产生 {len(approved_proposals)} 个通过审核的提案")
    else:
        # 输出有争议ideas列表
        if controversial_ideas:
            report = _generate_controversial_report(controversial_ideas)
            _save_output(output_dir, "controversial_ideas.md", report)
            print(f"📋 产生 {len(controversial_ideas)} 个有争议的ideas")
        else:
            print("📭 无有效提案，静默结束")


def _generate_ideas(client, config: dict, creative_config) -> list:
    """生成创新想法"""
    prompt = creative_config.system_prompt

    response = client.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=creative_config.user_prompt),
        ]
    )
    response_text = response.content

    # 解析想法
    ideas = []
    blocks = response_text.split("\n\n")
    for block in blocks:
        if "标题:" in block or "动机:" in block:
            ideas.append({"content": block, "debate_history": []})

    return ideas[: creative_config.max_ideas]


def _multi_round_debate(idea: dict, max_rounds: int, approval_config) -> dict:
    """多轮辩论审核（复用 shared/debate.py 的核心逻辑）"""
    current_round = 0
    approved = False
    debate_history = []

    while current_round < max_rounds:
        current_round += 1

        # 使用共享的并行评审逻辑
        review_results = run_parallel_review(
            content=idea["content"],
            current_round=current_round,
        )

        # 分析投票结果
        vote_result = analyze_votes([
            {"role": r["role"], "vote": r["vote"]}
            for r in review_results
        ])

        debate_history.append({
            "round": current_round,
            "yes": vote_result["yes"],
            "no": vote_result["no"],
            "abstain": vote_result["abstain"],
            "reviews": review_results,
        })

        # 检查是否通过
        approval = check_approval(
            vote_result,
            max_rounds,
            current_round,
            yes_votes_needed=approval_config.yes_votes_needed,
            no_votes_limit=approval_config.no_votes_limit,
            require_yes_over_no=approval_config.require_yes_over_no,
        )
        if approval["approved"]:
            approved = True
            break
        if approval["finished"]:
            break

    return {
        "idea": idea,
        "approved": approved,
        "debate_history": debate_history,
        "final_vote": debate_history[-1] if debate_history else None,
    }


def _generate_proposal_report(proposals: list) -> str:
    """生成提案报告"""
    report = f"""# 创新RFC提案报告

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 通过审核的提案

"""

    for i, prop in enumerate(proposals, 1):
        report += f"""### 提案 {i}

{prop["idea"]["content"]}

**辩论结果**: 赞成{prop["final_vote"]["yes"]} / 反对{prop["final_vote"]["no"]}

---
"""

    report += """
*由 EvolveRFC 夜间守护进程自动生成*
"""

    return report


def _generate_controversial_report(ideas: list) -> str:
    """生成有争议ideas报告"""
    report = f"""# 有争议的Ideas列表

生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

以下ideas未能通过多轮审核，但具有一定的讨论价值：

"""

    for i, idea in enumerate(ideas, 1):
        report += f"""### Idea {i}

{idea['content']}

---
"""

    report += """
请人类专家次日决策是否进一步讨论。

*由 EvolveRFC 夜间守护进程自动生成*
"""

    return report


def _save_output(output_dir: str, filename: str, content: str):
    """保存输出文件"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = Path(output_dir) / filename
    output_path.write_text(content, encoding="utf-8")
