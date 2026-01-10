"""控制台配置"""
from rich.console import Console
from rich.theme import Theme

# RFC 评审主题
RFCTheme = Theme({
    "title": "bold cyan",
    "subtitle": "italic yellow",
    "role.architekt": "green",
    "role.security": "red",
    "role.cost_control": "magenta",
    "role.innovator": "blue",
    "role.clerk": "white",
    "status.pending": "yellow",
    "status.active": "cyan",
    "status.done": "green",
    "status.error": "red",
    "vote.for": "green",
    "vote.against": "red",
    "vote.abstain": "yellow",
    "progress": "cyan",
    "panel.header": "bold cyan",
    "consensus": "green",
    "deadlock": "red",
})

# 全局控制台实例
console = Console(theme=RFCTheme, force_terminal=True)
