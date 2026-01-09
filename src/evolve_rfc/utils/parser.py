"""输出解析工具
"""

import re
from typing import TypedDict, Optional


class ReviewResult(TypedDict):
    """评审结果"""
    论点: str
    论据: list[str]
    针对议题: str
    立场: str
    置信度: float


def parse_agent_output(output: str) -> Optional[ReviewResult]:
    """解析智能体输出"""
    try:
        # 尝试解析YAML格式
        if "论点:" in output and "论据:" in output:
            result = {}

            # 提取论点
            论点_match = re.search(r'论点:\s*"([^"]+)"', output)
            if 论点_match:
                result["论点"] = 论点_match.group(1)
            else:
                result["论点"] = ""

            # 提取论据
            论据_match = re.search(r'论据:\s*\[([^\]]+)\]', output)
            if 论据_match:
                论据_str = 论据_match.group(1)
                result["论据"] = [e.strip().strip('"') for e in 论据_str.split(",")]
            else:
                result["论据"] = []

            # 提取针对议题
            针对_match = re.search(r'针对议题:\s*"([^"]+)"', output)
            if 针对_match:
                result["针对议题"] = 针对_match.group(1)
            else:
                result["针对议题"] = ""

            # 提取立场
            立场_match = re.search(r'立场:\s*(赞成|反对|弃权)', output)
            if 立场_match:
                result["立场"] = 立场_match.group(1)
            else:
                result["立场"] = "弃权"

            # 提取置信度
            置信度_match = re.search(r'置信度:\s*([0-9.]+)', output)
            if 置信度_match:
                result["置信度"] = float(置信度_match.group(1))
            else:
                result["置信度"] = 0.5

            return ReviewResult(**result)

        return None

    except Exception:
        return None


def parse_clerk_output(output: str) -> dict:
    """解析书记官输出"""
    result = {
        "consensus_points": [],
        "open_issues": [],
        "next_focus": [],
    }

    # 提取共识点
    consensus_section = re.search(
        r'## 共识点\s*\n(.*?)(?=##|$)',
        output,
        re.DOTALL,
    )
    if consensus_section:
        lines = consensus_section.group(1).strip().split("\n")
        result["consensus_points"] = [
            line.strip().lstrip("- ").strip()
            for line in lines
            if line.strip()
        ]

    # 提取分歧点
    disagreement_section = re.search(
        r'## 分歧点\s*\n(.*?)(?=##|$)',
        output,
        re.DOTALL,
    )
    if disagreement_section:
        lines = disagreement_section.group(1).strip().split("\n")
        result["open_issues"] = [
            line.strip().lstrip("- ").strip()
            for line in lines
            if line.strip()
        ]

    # 提取下一轮焦点
    focus_section = re.search(
        r'## 下一轮焦点\s*\n(.*?)(?=##|$)',
        output,
        re.DOTALL,
    )
    if focus_section:
        lines = focus_section.group(1).strip().split("\n")
        result["next_focus"] = [
            line.strip().lstrip("- ").strip()
            for line in lines
            if line.strip()
        ]

    return result
