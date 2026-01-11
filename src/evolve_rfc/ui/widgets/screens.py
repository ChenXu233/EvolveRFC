"""独立屏幕组件

提供可独立显示的屏幕：
- WelcomeScreen: 欢迎屏幕
"""

from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Static


WELCOME_TITLE = """
[bold cyan]
██████╗ ██╗   ██╗ ██████╗ ██╗    ██╗   ██╗███████╗██████╗ ███████╗██████╗ 
██╔═══╝ ██║   ██║██╔═══██╗██║    ██║   ██║██╔════╝██╔══██╗██╔════╝██╔═══╝ 
████╗   ██║   ██║██║   ██║██║    ██║   ██║█████╗  ██████╔╝█████╗  ██║     
██╔═╝   ╚██╗ ██╔╝██║   ██║██║    ╚██╗ ██╔╝██╔══╝  ██╔══██╗██╔══╝  ██║     
██████╗  ╚████╔╝ ╚██████╔╝███████╗╚████╔╝ ███████╗██║  ██║██║     ██████╗
╚═════╝   ╚═══╝   ╚═════╝ ╚══════╝ ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝     ╚═════╝
[/bold cyan]

[bold white]RFC 智能体协同评审系统[/]
"""

WELCOME_TEXT = """
🎯 [bold]模拟技术议会，多视角协同评审[/]
🔄 [bold]动态共识形成，多轮辩论投票[/]
🤖 [bold]AI 自主运作，人类最终决策[/]
"""


class WelcomeScreen(Screen):
    """欢迎屏幕"""

    CSS = """
    WelcomeScreen {
        align: center middle;
        background: rgba(0,0,0,0.8);
    }
    #welcome-container {
        width: 120;
        height: auto;
        border: thick cyan;
        padding: 2 4;
        background: $surface;
        align: center middle;
    }
    #welcome-title {
        text-align: center;
    }
    #welcome-text {
        text-align: center;
    }
    #enter-btn {
        width: 100%;
    }
    """

    BINDINGS = [
        ("enter", "app.pop_screen", "进入系统"),
        ("q", "app.quit", "退出"),
    ]

    def compose(self):
        with Container(id="welcome-container"):
            yield Static(WELCOME_TITLE, id="welcome-title")
            yield Static(WELCOME_TEXT, id="welcome-text")
            yield Button("🚀 进入系统 (Press Enter)", variant="primary", id="enter-btn")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "enter-btn":
            self.app.pop_screen()
