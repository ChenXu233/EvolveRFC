"""智能体基类
"""

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


@dataclass
class AgentResult:
    """智能体执行结果"""
    success: bool
    content: str
    error: Optional[str] = None


class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, llm_client: ChatOpenAI, system_prompt: str):
        self.llm_client = llm_client
        self.system_prompt = system_prompt

    @abstractmethod
    def run(self, input_text: str, context: Optional[dict] = None) -> AgentResult:
        """执行智能体逻辑"""
        pass

    def _build_messages(self, input_text: str, context: Optional[dict] = None) -> list:
        """构建消息列表（LangChain格式）"""
        messages = [
            SystemMessage(content=self.system_prompt),
        ]

        if context:
            context_text = "\n".join([f"{k}: {v}" for k, v in context.items()])
            messages.append(SystemMessage(content=f"上下文信息：\n{context_text}"))

        messages.append(HumanMessage(content=input_text))
        return messages
