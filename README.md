# EvolveRFC - RFC智能体协同评审系统

<div align="center">

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![LangGraph](https://img.shields.io/badge/langgraph-0.2+-purple.svg)
![OpenAI](https://img.shields.io/badge/openai-gpt--4o-green.svg)
![Anthropic](https://img.shields.io/badge/anthropic-claude-orange.svg)

</div>

## 项目简介

EvolveRFC 是一个基于多智能体系统的 RFC 自动化评审工作流。它模拟"技术议会"的辩论场景，对 RFC 草案进行多角度、深层次、可追溯的自动化评审，最终辅助人类架构师做出更高质效的决策。

## 核心特性

### 🌟 多智能体评审（动态配置）
系统内置 5 种角色，支持在配置文件中自由启用/禁用/添加：

| 角色 | 职责 | 投票权 | 默认 |
|------|------|--------|------|
| 首席架构师 | 评估架构设计、识别技术债务 | ✅ | 启用 |
| 安全偏执狂 | 发现安全和合规风险 | ✅ | 启用 |
| 成本控制型运维 | 关注部署成本和运维复杂度 | ✅ | 启用 |
| 激进创新派 | 挑战保守设计、提出创新建议 | ✅ | 启用 |
| 书记官 | 总结讨论、起草报告 | ❌ | 启用 |

### 🔄 动态议会制
- **多轮辩论**：支持最多 10 轮讨论，直至达成共识或超时
- **投票机制**：评审者对 RFC 表态（赞成/反对/弃权）
- **人类介入**：反对票超过 30% 或达到最大轮次时，请求人类裁决
- **事件溯源**：所有讨论记录以事件流形式存储，确保完整可追溯

### 🌙 夜间守护进程
- **深度审计模式** - 分析代码发现设计缺陷
- **现有RFC预讨论** - 半夜预讨论待评审RFC
- **创新提案模式** - 提出新RFC想法（需多轮审核）

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 PDM
pdm install
```

### 2. 配置 LLM

在 `config/workflow.yaml` 中配置 API 密钥：

```bash
export OPENAI_API_KEY="your-openai-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

全局 LLM 配置（所有角色默认使用）：
```yaml
llm:
  provider: openai        # openai | anthropic
  model: gpt-4o
  temperature: 0.7
```

### 3. 运行评审

```bash
# 交互式评审
uv run python -m evolve_rfc.workflow

# 夜间守护进程
uv run python -m evolve_rfc.nighty.daemon
```

## 动态角色配置

### 角色配置项

```yaml
roles:
  architect:
    enabled: true              # 是否启用此角色
    must_speak: true           # 是否必须发言
    can_vote: true             # 是否有投票权（可选，默认根据 must_speak 推断）
    prompt_file: prompts/architect.txt  # 提示词文件路径
    llm:                       # 可选：覆盖全局 LLM 设置
      provider: anthropic
      model: claude-sonnet-4-20250514
      temperature: 0.3
```

| 配置项 | 说明 |
|--------|------|
| `enabled` | 是否参与评审 |
| `must_speak` | 是否必须发言（不影响投票权） |
| `can_vote` | 是否有投票权，未指定时默认等于 `must_speak` |
| `prompt_file` | 提示词文件路径 |
| `llm.*` | 角色专属的 LLM 配置 |

### 添加自定义角色

1. **在 `config/workflow.yaml` 中添加角色配置**：
```yaml
roles:
  # ... 现有角色 ...

  # 新增性能优化专家
  performance:
    enabled: true
    must_speak: true
    can_vote: true
    prompt_file: prompts/performance.txt
```

2. **创建提示词文件** `prompts/performance.txt`：
```text
你是一个性能优化专家，关注系统的性能表现。

你的核心职责：
1. 评估代码的性能瓶颈
2. 检查资源使用效率
3. 识别优化机会

请评审 RFC 内容，输出以下格式：
论点: "<一句话核心观点>"
论据: ["<支撑论据1>", "<支撑论据2>"]
立场: "赞成|反对|弃权"
置信度: 0.0-1.0
```

3. **重启服务** - 新角色立即生效

### 禁用角色

将角色的 `enabled` 设置为 `false`：
```yaml
roles:
  innovator:
    enabled: false  # 禁用激进创新派
```

## 项目结构

```
EvolveRFC/
├── src/evolve_rfc/
│   ├── core/           # 核心模块：状态管理、路由器
│   ├── agents/         # 智能体：角色提示词、书记官
│   ├── workflow/       # LangGraph 工作流定义
│   ├── nightly/        # 夜间守护进程
│   ├── shared/         # 共享逻辑：辩论、投票分析
│   └── utils/          # 工具模块：配置、解析器
├── config/
│   ├── workflow.yaml   # 工作流配置（角色定义）
│   └── nightly.yaml    # 夜间守护进程配置
├── prompts/            # 角色提示词模板
└── tests/              # 单元测试
```

## 配置说明

### 工作流配置 (`config/workflow.yaml`)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `routing.max_rounds` | 10 | 最大讨论轮次 |
| `routing.round_timeout_minutes` | 30 | 人类决策超时时间 |
| `thresholds.deadlock_opposition_ratio` | 0.3 | 反对票超 30% 视为僵局 |
| `thresholds.consensus_quorum` | 0.8 | 80% 赞成即达成共识 |
| `llm.provider` | openai | LLM 提供商 |
| `llm.model` | gpt-4o | 模型名称 |
| `llm.temperature` | 0.7 | 温度参数 |

### 夜间配置 (`config/nightly.yaml`)

```yaml
nightly:
  trigger_hour: 0              # UTC 触发时间
  code_analysis:
    scope: "diff"              # 分析范围：diff 或 full
  rfc_pre_discussion:
    enabled: true
    max_rfcs_per_night: 5
  creative_proposal:
    enabled: true
    max_rounds: 5
    daily_output_limit: 1
  mode_weights:
    audit: 0.4
    pre_discussion: 0.3
    creative: 0.3
```

## 命令速查

| 命令 | 说明 |
|------|------|
| `uv run python -m evolve_rfc.workflow` | 运行 RFC 评审工作流 |
| `uv run python -m evolve_rfc.nightly.daemon` | 启动夜间守护进程 |
| `uv run pytest` | 运行所有测试 |
| `uv run ruff check .` | 代码风格检查 |
| `uv run mypy src/` | 类型检查 |

## GitHub Action 集成

1. 在 Repository Settings 中配置 `OPENAI_API_KEY` 或 `ANTHROPIC_API_KEY` Secret
2. 工作流会在每日 UTC 0:00 自动触发
3. 输出会自动创建 Pull Request

## 许可证

MIT License
