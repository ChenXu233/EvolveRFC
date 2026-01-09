"""创新提案模式

基于审计结果或自由发散，提出新RFC想法（需多轮智能体审核）。
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ...shared import run_parallel_review, analyze_votes, check_approval


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


def run_creative_mode(config: Dict[str, Any], output_dir: str):
    """运行创新提案模式"""
    print("💡 进入创新提案模式...")

    # 加载配置
    creative_config = config.get("nightly", {}).get("creative_proposal", {})
    max_rounds = creative_config.get("max_rounds", 5)

    # 生成创新想法
    client = _create_client()
    ideas = _generate_ideas(client, config)

    if not ideas:
        print("📭 无创新想法，静默结束")
        return

    # 多轮辩论审核（复用 shared/debate.py）
    approved_proposals = []
    for idea in ideas:
        result = _multi_round_debate(client, idea, max_rounds)
        if result["approved"]:
            approved_proposals.append(result)

    # 生成输出
    if approved_proposals:
        report = _generate_proposal_report(approved_proposals)
        _save_output(output_dir, "creative_proposal.md", report)
        print(f"✅ 产生 {len(approved_proposals)} 个通过审核的提案")
    else:
        # 输出有争议ideas列表
        controversial_list = [
            r["idea"] for r in [_multi_round_debate(client, idea, max_rounds) for idea in ideas]
            if not r["approved"]
        ]
        if controversial_list:
            report = _generate_controversial_report(controversial_list)
            _save_output(output_dir, "controversial_ideas.md", report)
            print(f"📋 产生 {len(controversial_list)} 个有争议的ideas")
        else:
            print("📭 无有效提案，静默结束")


def _generate_ideas(client: ChatOpenAI, config: dict) -> list:
    """生成创新想法"""
    prompt = """你是一个首席技术布道师，负责提出大胆但可行的改进想法。

基于以下上下文，提出1-3个创新RFC想法：
1. 当前项目技术栈
2. 行业趋势
3. 潜在改进方向

每个想法请输出：
- 标题：一句话描述
- 动机：为什么需要这个改进
- 核心方案：简要描述实现方案
- 预期收益：带来的价值

请直接输出，不要使用markdown格式。
"""

    response = client.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content="请提出创新RFC想法。"),
    ])
    response_text = response.content if hasattr(response, 'content') else str(response)

    # 解析想法
    ideas = []
    blocks = response_text.split("\n\n")
    for block in blocks:
        if "标题:" in block or "动机:" in block:
            ideas.append({"content": block, "debate_history": []})

    return ideas[:3]  # 最多3个


def _multi_round_debate(client: ChatOpenAI, idea: dict, max_rounds: int) -> dict:
    """多轮辩论审核（复用 shared/debate.py 的核心逻辑）"""
    current_round = 0
    approved = False
    debate_history = []

    while current_round < max_rounds:
        current_round += 1

        # 使用共享的并行评审逻辑
        review_results = run_parallel_review(
            client=client,
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
        approval = check_approval(vote_result, max_rounds, current_round)
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

{prop['idea']['content']}

**辩论结果**: 赞成{prop['final_vote']['赞成']} / 反对{prop['final_vote']['反对']}

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
