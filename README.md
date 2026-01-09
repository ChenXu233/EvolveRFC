# EvolveRFC - RFC智能体协同评审系统

<div align="center">

![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![PDM](https://img.shields.io/badge/pdm-managed-green.svg)
![LangGraph](https://img.shields.io/badge/langgraph-0.2+-purple.svg)

</div>

## 项目简介

EvolveRFC 是一个基于多智能体系统的 RFC 自动化评审工作流。它模拟"技术议会"的辩论场景，对 RFC 草案进行多角度、深层次、可追溯的自动化评审，最终辅助人类架构师做出更高质效的决策。

## 核心特性

### 🌟 多智能体评审
- **首席架构师** - 关注系统设计的长期扩展性和技术债务
- **安全偏执狂** - 发现所有潜在安全和合规风险
- **成本控制型运维** - 关注部署复杂性和资源消耗
- **激进创新派** - 挑战过于保守的设计决策
- **书记官** - 总结讨论、提炼共识、起草报告（不参与投票）

### 🔄 动态议会制
- 多轮辩论和投票机制
- 支持人类介入和最终裁决
- 事件溯源模式确保完整可追溯

### 🌙 夜间守护进程
- **深度审计模式** - 分析代码发现设计缺陷
- **现有RFC预讨论** - 半夜预讨论待评审RFC
- **创新提案模式** - 提出新RFC想法（需多轮审核）

## 快速开始

### 安装依赖

```bash
# 使用PDM
pdm install

# 或使用uv（推荐）
uv sync
```

### 配置

设置环境变量：
```bash
export MINIMAX_API_KEY="your-api-key"
export MINIMAX_BASE_URL="https://api.minimax.chat"  # 可选
```

### 运行评审工作流

```bash
uv run python -m evolve_rfc.workflow
```

### 运行夜间守护进程

```bash
# 本地模式
uv run python -m evolve_rfc.nightly.daemon

# 或使用脚本
bash scripts/run_nightly.sh
```

## 项目结构

```
EvolveRFC/
├── src/evolve_rfc/
│   ├── core/           # 核心模块：状态管理、路由器
│   ├── agents/         # 智能体：角色提示词、书记官
│   ├── workflow/       # LangGraph工作流定义
│   ├── nightly/        # 夜间守护进程
│   ├── llm/            # LLM接口（MiniMax封装）
│   └── utils/          # 工具模块：配置、解析器
├── config/             # 配置文件
├── prompts/            # 角色提示词模板
├── scripts/            # 启动脚本
├── tests/              # 单元测试
├── rfcs/               # RFC文档目录
└── nightly_output/     # 夜间守护进程输出
```

## 配置说明

### 工作流配置 (`config/workflow.yaml`)

```yaml
routing:
  max_rounds: 10              # 最大讨论轮次
  round_timeout_minutes: 30   # 人类决策超时时间

thresholds:
  deadlock_opposition_ratio: 0.3   # 反对票超30%视为僵局
  consensus_quorum: 0.8            # 80%赞成即达成共识
```

### 夜间守护进程配置 (`config/nightly.yaml`)

```yaml
nightly:
  code_analysis:
    scope: "diff"            # 分析范围：diff 或 full
    focus_dirs: ["src"]      # 聚焦目录

  mode_weights:              # 模式权重
    audit: 0.4
    pre_discussion: 0.3
    creative: 0.3

  output:
    max_output_per_night: 1  # 每日仅输出1个
```

## GitHub Action 集成

项目支持在 GitHub Action 中运行夜间守护进程：

1. 在 Repository Settings 中配置 `MINIMAX_API_KEY` Secret
2. 工作流会自动在每日 UTC 0:00 触发
3. 产生的输出会自动创建 Pull Request

## 测试

```bash
# 运行所有测试
uv run pytest

# 运行并查看覆盖率
uv run pytest --cov=src/evolve_rfc

# 运行特定测试
uv run pytest tests/test_state.py -v
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
