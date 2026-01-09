# CLAUDE.md

This file provides guidance to Claude Code when working with this project.

## Project Overview

EvolveRFC - RFC智能体协同评审系统

A multi-agent based RFC intelligent review system that simulates a "technical parliament" for automated RFC review. The system features:

- **Multi-perspective Analysis**: AI agents with different technical roles (architecture, security, operations) review RFCs concurrently
- **Dynamic Consensus Formation**: Multi-round debate and voting to form consensus
- **Human-in-the-Loop**: Human architects have final decision authority
- **Nightly Daemon**: Automated RFC proposal generation during off-hours

## Tech Stack

- **Language**: Python 3.11+
- **Package Manager**: PDM
- **Core Framework**: LangGraph
- **LLM**: MiniMax M2.1
- **Configuration**: YAML

## Project Structure

```
src/evolve_rfc/
├── core/           # State management & router
├── agents/         # Role prompts & agents
├── workflow/       # LangGraph workflow
├── nightly/        # Nightly daemon
├── llm/            # LLM client (MiniMax)
└── utils/          # Config & parsers
```

## Key Files

- `pyproject.toml` - Project configuration
- `config/workflow.yaml` - Workflow configuration
- `config/nightly.yaml` - Nightly daemon configuration
- `prompts/*.txt` - Role prompt templates

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src/

# Run nightly daemon
uv run python -m evolve_rfc.nightly.daemon
```

## Architecture Notes

### State Management (Event Sourcing)

All state changes are recorded as immutable events in `events` list. The state is derived from events.

```python
class DiscussionState(TypedDict):
    events: list[DiscussionEvent]  # Event stream (immutable)
    rfc_content: str
    current_round: int
    consensus_points: list
    open_issues: list
    # ...
```

### Router Pattern

Route logic is centralized in `WorkflowRouter` rather than scattered in nodes.

### Role System

- Reviewers (must vote): architect, security, cost_control, innovator
- Service (no vote): clerk (summarizes discussions only)

## Environment Variables

- `MINIMAX_API_KEY` - MiniMax API key
- `MINIMAX_BASE_URL` - MiniMax API base URL (optional)
