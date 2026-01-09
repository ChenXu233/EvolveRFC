"""书记官智能体

负责总结所有模型的发言、提炼共识/分歧、起草最终报告。
"""

from typing import Optional
from langchain_openai import ChatOpenAI
from ..agents.base import BaseAgent, AgentResult
from ..agents.roles import RoleType, get_role_prompt


class ClerkAgent(BaseAgent):
    """书记官智能体"""

    def __init__(self, llm_client: ChatOpenAI):
        super().__init__(llm_client, get_role_prompt(RoleType.CLERK))

    def run(
        self,
        round_summary: str,
        events: list,
        context: Optional[dict] = None,
    ) -> AgentResult:
        """执行书记官职责"""
        input_text = f"""请汇总本轮讨论结果。

本轮讨论摘要：
{round_summary}

参与讨论的角色发言：
"""

        for event in events:
            if hasattr(event, 'actor') and hasattr(event, 'content'):
                input_text += f"- {event.actor}: {event.content}\n"

        messages = self._build_messages(input_text, context)

        try:
            response = self.llm_client.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)
            return AgentResult(success=True, content=content)
        except Exception as e:
            return AgentResult(success=False, content="", error=str(e))

    def generate_final_report(
        self,
        all_events: list,
        consensus_points: list,
        open_issues: list,
        rfc_content: str,
    ) -> AgentResult:
        """生成最终RFC评审报告"""
        input_text = f"""请生成最终的RFC评审报告。

原始RFC内容：
{rfc_content}

已达成共识的条目：
{chr(10).join([f"- {p}" for p in consensus_points]) if consensus_points else "无"}

待决议项：
{chr(10).join([f"- {i}" for i in open_issues]) if open_issues else "无"}

完整讨论历史已记录在事件流中。

请生成格式规范的RFC评审报告，包括：
1. 执行摘要
2. 共识点总结
3. 分歧点分析
4. 最终建议
5. 附录：完整讨论记录引用
"""

        messages = self._build_messages(input_text)

        try:
            response = self.llm_client.invoke(messages)
            content = response.content if hasattr(response, 'content') else str(response)
            return AgentResult(success=True, content=content)
        except Exception as e:
            return AgentResult(success=False, content="", error=str(e))
