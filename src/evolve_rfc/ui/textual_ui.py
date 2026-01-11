"""Textual 版流式 UI（替代 Rich Live）.

设计要点：
- 在独立线程中运行 Textual App，主线程可随时调用 `add_chunk` / `finish` / `update_tokens`。
- 左侧 RichLog 实时追加内容；右侧 DataTable 展示 Token 统计。
- 终端宽度不足时，Textual 自适应，避免 Rich Live 的换行/重复渲染问题。

使用方法（示例）：
    ui = TextualStreamingUI()
    ui.start()
    ui.add_chunk("architect", "hello")
    ui.update_tokens({...})
    ui.finish(vote="赞成")
    ui.stop()

注意：需要 `textual` 依赖；在 pyproject.toml 中添加 textual>=0.55。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Header, Footer, RichLog, Static, DataTable


@dataclass
class TokenStats:
    role: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    remaining: int = 0
    max_tokens: int = 0
    usage_percent: float = 0.0


class RFCApp(App):
    """Textual 主应用，包含日志与 token 监控。"""

    CSS = """
    Screen {
        layout: vertical;
    }
    .main {
        height: 1fr;
    }
    RichLog {
        border: solid $accent 1;
    }
    #token {
        width: 40;
        min-width: 32;
        border: solid $accent 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._rich_log: RichLog | None = None
        self._token_table: DataTable | None = None
        self._last_role: str | None = None
        self._last_vote: str | None = None
        self._token_rows: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="main"):
            self._rich_log = RichLog(markup=True, wrap=True, highlight=False)
            self._token_table = DataTable(id="token")
            self._token_table.add_columns("角色", "输入", "输出", "合计", "%", "剩余")
            yield self._rich_log
            yield self._token_table
        yield Footer()

    # ---- 对外更新 API（供 call_from_thread 调用） -----------------
    def post_chunk(self, role: str, chunk: str) -> None:
        if not chunk:
            return
        if self._rich_log is None:
            return
        prefix = "" if self._last_role == role else f"\n[{role}] "
        self._rich_log.write(prefix + chunk, scroll_end=True)
        self._last_role = role

    def post_finish(self, vote: Optional[str], tool_calls: Optional[list] = None) -> None:
        if self._rich_log is None:
            return
        vote_text = vote or "待投票"
        self._rich_log.write(f"\n[bold green]✓ 结束[/] 投票: {vote_text}\n", scroll_end=True)
        
        self._last_vote = vote_text

    def post_tokens(self, stats: TokenStats) -> None:
        if self._token_table is None:
            return
        row_data: tuple[Any, ...] = (
            stats.role,
            f"{stats.input_tokens:,}",
            f"{stats.output_tokens:,}",
            f"{stats.total_tokens:,}",
            f"{stats.usage_percent:.1f}%",
            f"{stats.remaining:,}",
        )
        if stats.role in self._token_rows:
            row_key = self._token_rows[stats.role]
            self._token_table.remove_row(row_key)
            new_row_key = self._token_table.add_row(*row_data)
            self._token_rows[stats.role] = new_row_key
        else:
            row_key = self._token_table.add_row(*row_data)
            self._token_rows[stats.role] = row_key

    # ---- 处理退出：允许 ESC 退出 ----------------------------------
    async def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            await self.action_quit()


class TextualStreamingUI:
    """线程安全的 Textual UI 包装器."""

    def __init__(self):
        self._app = RFCApp()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._app.run, daemon=True)
        self._thread.start()

    def add_chunk(self, role: str, chunk: str):
        self._app.call_from_thread(self._app.post_chunk, role, chunk)

    def finish(self, vote: Optional[str] = None, tool_calls: Optional[list] = None):
        stats = TokenStats(
            role="",
        )
        self._app.call_from_thread(self._app.post_finish, vote, tool_calls)

    def update_tokens(self, token_data: dict):
        stats = TokenStats(
            role=token_data.get("role", "unknown"),
            input_tokens=token_data.get("input_tokens", 0),
            output_tokens=token_data.get("output_tokens", 0),
            total_tokens=token_data.get("total_tokens", 0),
            remaining=token_data.get("remaining", 0),
            max_tokens=token_data.get("max_tokens", 0),
            usage_percent=token_data.get("usage_percent", 0.0),
        )
        self._app.call_from_thread(self._app.post_tokens, stats)

    def stop(self):
        self._app.call_from_thread(self._app.exit)
        if self._thread:
            self._thread.join(timeout=1)
