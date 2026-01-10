"""角色提示词库 - 动态配置版

角色从 config/workflow.yaml 读取，支持动态添加/删除。
"""

from pathlib import Path

# 类型别名：角色名用字符串表示
# 兼容旧代码：RoleType = str
RoleType = str

# 提示词文件路径
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# 默认角色定义（回退用）
DEFAULT_ROLES: list[dict] = [
    {
        "name": "architect",
        "enabled": True,
        "must_speak": True,
        "prompt_file": "prompts/architect.txt",
        "is_voter": True,
    },
    {
        "name": "security",
        "enabled": True,
        "must_speak": True,
        "prompt_file": "prompts/security.txt",
        "is_voter": True,
    },
    {
        "name": "cost_control",
        "enabled": True,
        "must_speak": True,
        "prompt_file": "prompts/cost_control.txt",
        "is_voter": True,
    },
    {
        "name": "innovator",
        "enabled": True,
        "must_speak": False,
        "prompt_file": "prompts/innovator.txt",
        "is_voter": True,
    },
    {
        "name": "clerk",
        "enabled": True,
        "must_speak": False,
        "prompt_file": "prompts/clerk.txt",
        "is_voter": False,
    },
]


def _load_roles_from_config() -> list[dict]:
    """从配置文件加载角色配置

    加载规则：
    - 优先使用配置文件中的值
    - can_vote 未指定时，使用 DEFAULT_ROLES 中的默认值（保证向后兼容）
    - prompt_file 未指定时，使用 "prompts/{role_name}.txt"
    """
    from ..settings import get_settings

    settings = get_settings()
    config = settings.workflow.roles

    if not config:
        # 配置为空，使用默认值
        return [r for r in DEFAULT_ROLES if r["enabled"]]

    # 构建默认值的查找表
    default_map = {r["name"]: r for r in DEFAULT_ROLES}

    roles = []
    for name, role_config in config.items():
        if role_config.enabled:
            defaults = default_map.get(name, {})
            # can_vote 未指定时，使用默认值（向后兼容）
            if role_config.can_vote is not None:
                can_vote = role_config.can_vote
            else:
                can_vote = defaults.get("is_voter", role_config.must_speak)

            roles.append({
                "name": name,
                "enabled": True,
                "must_speak": role_config.must_speak,
                "prompt_file": role_config.prompt_file or defaults.get("prompt_file", f"prompts/{name}.txt"),
                "is_voter": can_vote,
            })
    return roles


def get_role_prompt(role: RoleType) -> str:
    """获取角色提示词

    Args:
        role: 角色名，如 "architect", "security", "clerk" 等
    """
    prompt_file = PROMPTS_DIR / f"{role}.txt"

    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    # 返回默认提示词
    return _get_default_prompt(role)


def _get_default_prompt(role: RoleType) -> str:
    """获取默认提示词（备用）"""
    default_prompts = {
        "architect": """你是一个首席架构师，关注系统设计的长期扩展性、简洁性和技术债务。

你的核心职责：
1. 评估RFC的架构设计是否合理
2. 识别潜在的技术债务
3. 检查是否符合SOLID原则
4. 评估长期扩展性

请评审RFC内容，输出以下格式（必须严格遵循）：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
针对议题: "<议题ID或标题>"
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
""",
        "security": """你是一个安全偏执狂，默认不信任任何设计，致力于发现所有潜在安全和合规风险。

你的核心职责：
1. 识别安全漏洞和攻击面
2. 检查数据保护和隐私合规
3. 评估认证授权机制
4. 发现潜在的注入攻击风险

请评审RFC内容，输出以下格式（必须严格遵循）：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
针对议题: "<议题ID或标题>"
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
""",
        "cost_control": """你是一个成本控制型运维，关注部署复杂性、监控成本、资源消耗和故障恢复。

你的核心职责：
1. 评估基础设施成本
2. 检查运维复杂度
3. 评估监控和可观测性
4. 检查故障恢复能力

请评审RFC内容，输出以下格式（必须严格遵循）：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
针对议题: "<议题ID或标题>"
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
""",
        "innovator": """你是一个激进创新派，推崇新技术、新模式，挑战过于保守的设计。

你的核心职责：
1. 评估引入新技术的可能性
2. 检查是否可以利用现代工具提升效率
3. 挑战过于保守的设计决策
4. 提出创新性改进建议

请评审RFC内容，输出以下格式（必须严格遵循）：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
针对议题: "<议题ID或标题>"
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
""",
        "clerk": """你是书记官，仅负责总结所有模型的发言、提炼共识/分歧、起草最终报告。

你的核心职责：
1. 汇总各方论点（不发表观点）
2. 提炼共识点与分歧点
3. 判定哪些议题已达成共识
4. 为下一轮准备焦点议题
5. 起草最终报告

你的行为准则：
- 从不参与投票
- 从不发表技术观点
- 保持中立，仅作为信息整理者

请汇总本轮讨论：
## 共识点
- [...]

## 分歧点
- [...]

## 待决议项
- [...]

## 下一轮焦点
- [...]
""",
    }

    return default_prompts.get(role, f"未知角色: {role}")


def get_all_roles() -> list[str]:
    """获取所有配置的角色名（启用 + 禁用）"""
    settings_roles = set(_load_roles_from_config() + DEFAULT_ROLES)
    return sorted(set(r["name"] for r in settings_roles))


def get_active_roles() -> list[str]:
    """获取所有启用的角色名"""
    return [r["name"] for r in _load_roles_from_config()]


def get_reviewer_roles() -> list[str]:
    """获取所有评审者角色（需要投票的）"""
    return [r["name"] for r in _load_roles_from_config() if r["is_voter"]]


def is_voter(role: str) -> bool:
    """判断角色是否需要投票"""
    for r in _load_roles_from_config():
        if r["name"] == role:
            return r["is_voter"]
    # 未配置的角色，默认不是投票者
    return False
