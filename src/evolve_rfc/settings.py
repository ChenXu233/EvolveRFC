"""配置管理 - 使用 Pydantic Settings

支持从 config/*.yaml 配置文件读取。
"""
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr, model_validator


ProviderType = Literal["openai", "anthropic"]


class BaseLLMConfig(BaseModel):
    """LLM 基础配置"""
    provider: ProviderType = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    base_url: Optional[str] = None  # 自定义 API 地址（用于代理或第三方兼容 API）
    timeout: Optional[float] = None  # Anthropic 超时时间（秒）
    stop: Optional[List[str]] = None  # Anthropic 停止词
    api_key: Optional[SecretStr] = None  # API 密钥（敏感信息，会被 .gitignore 忽略）

    @model_validator(mode="before")
    @classmethod
    def convert_api_key_to_secret_str(cls, data: dict) -> dict:
        """自动将字符串类型的 api_key 转换为 SecretStr"""
        if isinstance(data, dict) and "api_key" in data:
            api_key = data["api_key"]
            if isinstance(api_key, str):
                data["api_key"] = SecretStr(api_key)
        return data


class RoleConfig(BaseModel):
    """角色配置"""
    enabled: bool = True
    must_speak: bool = False  # 是否必须发言
    can_vote: Optional[bool] = None  # 是否有投票权，默认根据 must_speak 自动推断
    prompt_file: str = ""
    # 可选：覆盖全局 LLM 设置（包括 provider, model, temperature, base_url, api_key 等）
    llm: Optional[BaseLLMConfig] = None


class RoutingConfig(BaseModel):
    """路由配置"""
    max_rounds: int = 10
    round_timeout_minutes: int = 30


class ThresholdsConfig(BaseModel):
    """阈值配置"""
    deadlock_opposition_ratio: float = 0.3
    consensus_quorum: float = 0.8


class WorkflowConfig(BaseModel):
    """工作流配置"""
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    roles: Dict[str, RoleConfig] = Field(default_factory=dict)
    llm: BaseLLMConfig = Field(default_factory=BaseLLMConfig)


class CodeAnalysisConfig(BaseModel):
    """代码分析配置"""
    scope: str = "diff"
    focus_dirs: List[str] = Field(default_factory=lambda: ["src"])
    # 提示词配置
    system_prompt: str = (
        "你是一个苛刻的代码审查员。分析以下代码，目标是找出：\n"
        "1. 设计反模式（单点故障、紧耦合、过度复杂、违反SOLID）\n"
        "2. 潜在缺陷（资源泄漏、并发问题、安全漏洞、未处理边界）\n"
        "3. 技术债务（重复代码、硬编码、魔法数字、缺失注释/测试）\n\n"
        "请输出JSON格式：\n"
        "{\n"
        '  "问题列表": [\n'
        "    {\n"
        '      "文件": "路径",\n'
        '      "行号": 行号,\n'
        '      "描述": "问题描述",\n'
        '      "严重性": "高|中|低",\n'
        '      "改进建议": "一句话建议"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    user_prompt_template: str = "文件: {file_path}\n\n{file_content}"
    max_files_analyze: int = 10


class RFCPreDiscussionConfig(BaseModel):
    """RFC 预讨论配置"""
    enabled: bool = True
    max_rfcs_per_night: int = 5
    # 提示词配置
    system_prompt: str = (
        "你是一个预讨论智能体，负责对RFC草案进行快速预审。\n\n"
        "请从以下角度快速评审：\n"
        "1. 核心观点是否清晰\n"
        "2. 主要优点\n"
        "3. 潜在风险点\n"
        "4. 建议修改\n\n"
        "输出格式：\n"
        "```yaml\n"
        "rfc_id: \"RFC文件名\"\n"
        "rfc_title: \"标题\"\n"
        "预审摘要:\n"
        "  核心观点: \"一句话总结\"\n"
        "  优点: [\"优点1\", \"优点2\"]\n"
        "  风险点: [\"风险1\", \"风险2\"]\n"
        "  建议修改: [\"建议1\", \"建议2\"]\n"
        "投票结果:\n"
        "  赞成: 2\n"
        "  反对: 1\n"
        "  弃权: 0\n"
        "```\n"
    )
    user_prompt_template: str = "RFC文件: {rfc_path}\n\n{rfc_content}"


class CreativeProposalConfig(BaseModel):
    """创新提案配置"""
    enabled: bool = True
    max_rounds: int = 5
    daily_output_limit: int = 1
    # 通过条件配置（结构化）
    yes_votes_needed: int = 2  # 需要的最少赞成票
    no_votes_limit: int = 2    # 反对票上限（超过此值淘汰）
    require_yes_over_no: bool = True  # 是否要求赞成票多于反对票
    # 代码路径配置（用于智能体阅读参考）
    code_review_paths: List[str] = Field(default_factory=lambda: ["src"])
    # 提示词配置
    system_prompt: str = (
        "你是一个首席技术布道师，负责提出大胆但可行的改进想法。\n\n"
        "基于以下上下文，提出1-3个创新RFC想法：\n"
        "1. 当前项目技术栈\n"
        "2. 行业趋势\n"
        "3. 潜在改进方向\n\n"
        "每个想法请输出：\n"
        "- 标题：一句话描述\n"
        "- 动机：为什么需要这个改进\n"
        "- 核心方案：简要描述实现方案\n"
        "- 预期收益：带来的价值\n\n"
        "请直接输出，不要使用markdown格式。"
    )
    user_prompt: str = "请提出创新RFC想法。"
    max_ideas: int = 3


class ModeWeightsConfig(BaseModel):
    """模式权重配置"""
    audit: float = 0.4
    pre_discussion: float = 0.3
    creative: float = 0.3


class OutputConfig(BaseModel):
    """输出配置"""
    notify_on_empty: bool = False
    max_output_per_night: int = 1


class MCPConfig(BaseModel):
    """MCP Server 配置"""
    host: str = "127.0.0.1"  # 监听地址
    port: int = 8888  # 监听端口


class NightlyConfig(BaseModel):
    """夜间守护进程配置"""
    trigger_hour: int = 0
    code_analysis: CodeAnalysisConfig = Field(default_factory=CodeAnalysisConfig)
    rfc_pre_discussion: RFCPreDiscussionConfig = Field(default_factory=RFCPreDiscussionConfig)
    creative_proposal: CreativeProposalConfig = Field(default_factory=CreativeProposalConfig)
    mode_weights: ModeWeightsConfig = Field(default_factory=ModeWeightsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class Settings(BaseModel):
    """全局配置"""
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    nightly: NightlyConfig = Field(default_factory=NightlyConfig)


def _load_yaml_config(config_path: Path) -> Dict[str, Any]:
    """从 YAML 文件加载配置"""
    import yaml

    if not config_path.exists():
        return {}

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache()
def get_settings(config_dir: str = "config") -> Settings:
    """获取全局配置（单例模式）"""
    config_path = Path(config_dir)

    # 1. 加载 workflow.yaml
    workflow_config = _load_yaml_config(config_path / "workflow.yaml")

    # 2. 加载 nightly.yaml
    nightly_config = _load_yaml_config(config_path / "nightly.yaml")

    # 3. 加载 mcp.yaml
    mcp_config = _load_yaml_config(config_path / "mcp.yaml")

    # 4. 构建配置对象
    # 注意：workflow.yaml 的结构是根级别直接放置配置，不需要再嵌套 "workflow" key
    settings = Settings(
        mcp=MCPConfig(**mcp_config),
        workflow=WorkflowConfig(**workflow_config),
        nightly=NightlyConfig(**nightly_config.get("nightly", {})),
    )

    return settings


def reload_settings() -> Settings:
    """重新加载配置（清除缓存后获取）"""
    get_settings.cache_clear()
    return get_settings()


def get_role_llm_config(role_name: str) -> BaseLLMConfig:
    """获取角色的 LLM 配置

    合并逻辑：角色的配置覆盖全局配置，未配置的字段使用全局默认值
    优先级：角色配置 > 全局配置

    API 密钥优先级：角色配置 > 环境变量 > 全局配置
    """
    import os

    settings = get_settings()
    global_config = settings.workflow.llm
    role_config = settings.workflow.roles.get(role_name)

    # 获取角色的 LLM 配置（角色覆盖全局）
    if role_config and role_config.llm:
        merged = global_config.model_copy(
            update=role_config.llm.model_dump(exclude_unset=True)
        )
    else:
        merged = global_config

    # 合并 API 密钥（优先级：角色配置 > 环境变量 > 全局）
    if merged.api_key is None:
        provider = merged.provider
        env_key = None
        if provider == "openai":
            env_key = os.environ.get("OPENAI_API_KEY")
        elif provider == "anthropic":
            env_key = os.environ.get("ANTHROPIC_API_KEY")

        if env_key:
            merged.api_key = SecretStr(env_key)
        elif global_config.api_key:
            merged.api_key = global_config.api_key

    return merged
