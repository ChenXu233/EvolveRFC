"""EvolveRFC 主 Textual 应用

这是应用的入口点，负责组装各个 UI 组件。
UI 组件已拆分到 widgets/ 目录中：
- panels.py: 数据面板（角色状态、投票结果、Token统计）
- panes.py: 功能页面（评审页、夜间守护、设置）
- screens.py: 独立屏幕（欢迎页）
"""

from pathlib import Path
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from evolve_rfc.settings import get_settings
from evolve_rfc.workflow.graph import build_review_workflow
from evolve_rfc.workflow.nodes import (
    stream_callback_var,
    token_callback_var,
    log_callback_var,
    workflow_state_callback_var,
    finish_callback_var,
    _review_running_var,
    get_latest_saved_state,
    save_workflow_state,
)
from evolve_rfc.core.state import DiscussionState, create_initial_state
from evolve_rfc.ui.widgets import (
    WelcomeScreen,
    WorkflowStatusPanel,
)


class EvolveRFCApp(App):
    """EvolveRFC 主程序"""

    # 用于控制评审线程的标志
    _review_running = False
    _review_worker = None
    _saved_state_path = None  # 保存的状态文件路径

    CSS = """
    /* 基础样式 */
    Screen {
        background: $surface;
    }

    /* Tab 样式 */
    TabbedContent > .tab-bar {
        background: $panel;
    }

    TabbedContent > .tab-content {
        background: $surface;
    }

    /* 面板通用样式 */
    .panel {
        border: solid $primary;
        height: 100%;
    }

    .panel-title {
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
        text-align: center;
    }

    .panel-title-small {
        background: $secondary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    .stat-label {
        width: 10;
        height: auto;
        padding: 0 1;
        text-style: bold;
    }

    .stat-table {
        height: 8;
        width: 1fr;
    }

    #stats-row1, #stats-row2 {
        height: auto;
    }

    .pane-title {
        background: $accent;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }

    /* 日志区域 */
    .log-content {
        height: 100%;
        background: $surface;
        color: $text;
    }

    /* 表格区域 */
    .table-content {
        height: 100%;
    }

    /* 树形配置 */
    .tree-content {
        height: 100%;
    }

    /* 状态文本 */
    #review_status, #nightly_status {
        margin-left: 2;
        padding: 1;
        color: $text-muted;
    }

    /* 路径标签 */
    #path-label {
        margin-right: 1;
        text-style: bold;
    }

    /* 控件区域 */
    #review-controls, #nightly-controls {
        height: auto;
        min-height: 3;
        padding: 1;
        background: $panel;
        border-bottom: solid $primary;
    }

    #review-controls > *, #nightly-controls > * {
        margin-right: 1;
        height: auto;
    }

    #review-controls Label, #review-controls Input, #review-controls Button, #review-controls Static {
        height: auto;
    }

    #rfc_path {
        width: 30;
    }

    /* 主内容区域 */
    #review-main {
        height: 1fr;
    }

    #log-area {
        width: 70%;
        height: 100%;
    }

    #log-area VerticalScroll {
        height: 1fr;
    }

    #info-area {
        width: 30%;
    }

    #monitor-content {
        height: 1fr;
    }

    .stat-header {
        background: $secondary;
        color: $text;
        padding: 0 1;
        text-style: bold;
        height: auto;
    }

    .monitor-table {
        height: auto;
        max-height: 10;
    }

    /* 日志容器 */
    #nightly-log-container {
        height: 1fr;
    }

    #nightly-log-container VerticalScroll {
        height: 1fr;
    }

    /* 设置容器 */
    #settings-container {
        height: 100%;
    }

    /* 数据表格样式 */
    DataTable {
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "退出"),
        ("f1", "switch_tab('review')", "评审"),
        ("f2", "switch_tab('nightly')", "夜间"),
        ("f3", "switch_tab('settings')", "设置"),
        ("enter", "", "Enter")  # 防止 Enter 传播
    ]

    def on_mount(self):
        self.push_screen(WelcomeScreen())
        self.call_after_refresh(self._init_token_columns)

    def _init_token_columns(self):
        """初始化 Token 表格列"""
        try:
            token_table = self.query_one("#token_table", DataTable)
            if not token_table.columns:
                token_table.add_columns("角色", "输入", "输出", "合计", "%")
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="review"):
            with TabPane("RFC 评审", id="review"):
                with Horizontal(id="review-controls"):
                    yield Label("📄 RFC 路径:", id="path-label")
                    yield Input(placeholder="rfcs/example.md", value="rfcs/example.md", id="rfc_path")
                    yield Button("🚀 开始评审", id="start_review_btn", variant="primary")
                    yield Button("⏹ 停止评审", id="stop_review_btn", variant="error", disabled=True)
                    yield Button("📥 恢复进度", id="resume_review_btn", variant="default")
                    yield Static("就绪", id="review_status")
                with Horizontal(id="review-main"):
                    with VerticalScroll(id="log-area", classes="panel"):
                        yield Label("📜 实时日志", classes="panel-title")
                        yield RichLog(id="review_log", markup=True, wrap=True, classes="log-content", auto_scroll=False, max_lines=5000)
                    with Vertical(id="info-area", classes="panel"):
                        yield Label("📊 监控面板", classes="panel-title-small")
                        with VerticalScroll(id="monitor-content"):
                            yield WorkflowStatusPanel(id="workflow_panel")
                            yield Label("🗳️ 投票结果", classes="stat-header")
                            yield DataTable(id="voting_table", classes="monitor-table")
                            yield Label("💰 Token 统计", classes="stat-header")
                            yield DataTable(id="token_table", classes="monitor-table")
            with TabPane("夜间守护", id="nightly"):
                with Horizontal(id="nightly-controls"):
                    yield Label("🌙 夜间守护进程", classes="pane-title")
                    yield Button("▶ 启动守护", id="start_nightly", variant="warning")
                    yield Button("⏹ 停止", id="stop_nightly", variant="error", disabled=True)
                    yield Static("状态: 停止", id="nightly_status")
                with VerticalScroll(id="nightly-log-container", classes="panel"):
                    yield Label("📋 运行日志", classes="panel-title")
                    yield RichLog(id="nightly_log", markup=True, highlight=True, classes="log-content", auto_scroll=False, max_lines=5000)
            with TabPane("系统设置", id="settings"):
                with Vertical(id="settings-container"):
                    yield Label("⚙️ 系统配置", classes="pane-title")
                    yield Label("⚙️ 系统设置", classes="panel-title")
                    yield Static("系统配置查看功能已移动到 widgets/SettingsPane", classes="desc")
        yield Footer()

    def action_switch_tab(self, tab_id: str):
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

    @on(Button.Pressed, "#start_review_btn")
    def on_start_review(self):
        path_input = self.query_one("#rfc_path", Input)
        review_log = self.query_one("#review_log", RichLog)
        start_btn = self.query_one("#start_review_btn", Button)
        stop_btn = self.query_one("#stop_review_btn", Button)
        status = self.query_one("#review_status", Static)

        path = path_input.value

        if not path:
            review_log.write("[red]❌ 请输入路径[/]")
            return

        p = Path(path)
        if not p.exists():
            review_log.write(f"[red]❌ 文件不存在: {path} (当前目录: {Path.cwd()})[/]")
            return

        start_btn.disabled = True
        stop_btn.disabled = False
        status.update("[yellow]运行中...[/]")
        self._review_running = True
        self.run_review(str(p))

    @on(Button.Pressed, "#stop_review_btn")
    def on_stop_review(self):
        """停止评审"""
        self._review_running = False
        # 同时设置上下文变量，以便节点中也能检测到停止信号
        _review_running_var.set(False)
        review_log = self.query_one("#review_log", RichLog)
        start_btn = self.query_one("#start_review_btn", Button)
        stop_btn = self.query_one("#stop_review_btn", Button)
        status = self.query_one("#review_status", Static)

        review_log.write("[yellow]⏹ 正在停止评审...[/]")

        start_btn.disabled = False
        stop_btn.disabled = True
        status.update("[red]已停止[/]")

    @on(Button.Pressed, "#resume_review_btn")
    def on_resume_review(self):
        """恢复评审进度"""
        review_log = self.query_one("#review_log", RichLog)
        start_btn = self.query_one("#start_review_btn", Button)
        stop_btn = self.query_one("#stop_review_btn", Button)
        status = self.query_one("#review_status", Static)
        resume_btn = self.query_one("#resume_review_btn", Button)

        # 查找保存的状态
        saved_path, saved_state, save_reason = get_latest_saved_state()
        
        if not saved_state:
            review_log.write("[yellow]⚠️ 没有找到保存的评审进度[/]")
            return

        review_log.write(f"[bold]📥 找到保存的进度: 第 {saved_state.get('current_round', 1)} 轮[/]")
        review_log.write(f"   保存原因: {save_reason}")
        review_log.write("[bold]继续评审...[/]\n")

        # 禁用恢复按钮，启用停止按钮
        resume_btn.disabled = True
        start_btn.disabled = True
        stop_btn.disabled = False
        status.update("[yellow]恢复中...[/]")
        self._review_running = True
        self._saved_state_path = saved_path
        
        # 使用恢复的状态运行评审
        self.run_review_with_state(saved_state)

    @work(thread=True)
    def run_review(self, path: str) -> None:
        """后台运行评审流程 - 使用 LangGraph 工作流"""
        import threading

        app = self.app
        
        # 设置运行标志
        _review_running_var.set(True)

        # 设置回调变量（需要在每个线程中设置）
        token_stats_map: dict = {}
        token_stats_map_lock = threading.Lock()

        def stream_cb(role: str, chunk: str):
            """流式输出回调"""
            app.call_from_thread(self._stream_update, role, chunk)

        def token_cb(data: dict):
            """Token 统计回调"""
            role = data.get("role", "unknown")
            with token_stats_map_lock:
                token_stats_map[role] = data
            app.call_from_thread(self._update_token_display, token_stats_map)

        def log_cb(msg: str):
            """日志回调"""
            app.call_from_thread(self._log_review, msg)

        def workflow_state_cb(stage: str, round_num: int, role_data: dict):
            """工作流状态回调"""
            app.call_from_thread(self._update_workflow_panel, stage, round_num, role_data)
            if role_data.get("role"):
                app.call_from_thread(self._update_workflow_role, role_data.get("role"), role_data.get("status", "idle"))

        # 在当前线程的 context 中设置回调
        token_callback_var.set(token_cb)
        log_callback_var.set(log_cb)
        workflow_state_callback_var.set(workflow_state_cb)

        # 尝试设置 stream_callback_var，使用 copy_context 以便在子线程中访问
        try:
            from contextvars import copy_context
            ctx = copy_context()
            def stream_wrapper(role: str, chunk: str):
                ctx.run(stream_cb, role, chunk)
            stream_callback_var.set(stream_wrapper)
        except Exception:
            stream_callback_var.set(stream_cb)

        app.call_from_thread(self._update_workflow_panel, "init", 1, {})

        # 加载配置
        try:
            settings = get_settings()
            max_rounds = settings.workflow.routing.max_rounds
        except Exception as e:
            app.call_from_thread(self._log_review, f"[red]配置加载错误: {e}[/]")
            app.call_from_thread(self._finish_review)
            return

        # 读取 RFC 内容
        try:
            with open(path, "r", encoding="utf-8") as f:
                rfc_content = f.read()
        except Exception as e:
            app.call_from_thread(self._log_review, f"[red]读取出错: {e}[/]")
            app.call_from_thread(self._finish_review)
            return

        # 构建并运行工作流
        try:
            app.call_from_thread(self._log_review, "[bold]开始 RFC 评审...[/]\n")

            # 创建初始状态
            initial_state = create_initial_state(rfc_content, max_rounds)

            # 构建工作流
            workflow = build_review_workflow(max_rounds)

            # 运行工作流
            self._run_workflow(workflow, initial_state, app, token_stats_map)

        except Exception as e:
            app.call_from_thread(self._log_review, f"[red]评审过程异常: {e}[/]")
            import traceback
            app.call_from_thread(self._log_review, f"[dim]{traceback.format_exc()}[/]")

        app.call_from_thread(self._finish_review)

    @work(thread=True)
    def run_review_with_state(self, state: "DiscussionState") -> None:
        """使用保存的状态恢复评审流程"""
        import threading

        app = self.app
        
        # 设置运行标志
        _review_running_var.set(True)

        # 设置回调变量（需要在每个线程中设置）
        token_stats_map: dict = {}
        token_stats_map_lock = threading.Lock()

        def stream_cb(role: str, chunk: str):
            """流式输出回调"""
            app.call_from_thread(self._stream_update, role, chunk)

        def token_cb(data: dict):
            """Token 统计回调"""
            role = data.get("role", "unknown")
            with token_stats_map_lock:
                token_stats_map[role] = data
            app.call_from_thread(self._update_token_display, token_stats_map)

        def log_cb(msg: str):
            """日志回调"""
            app.call_from_thread(self._log_review, msg)

        def workflow_state_cb(stage: str, round_num: int, role_data: dict):
            """工作流状态回调"""
            app.call_from_thread(self._update_workflow_panel, stage, round_num, role_data)
            if role_data.get("role"):
                app.call_from_thread(self._update_workflow_role, role_data.get("role"), role_data.get("status", "idle"))

        # 在当前线程的 context 中设置回调
        token_callback_var.set(token_cb)
        log_callback_var.set(log_cb)
        workflow_state_callback_var.set(workflow_state_cb)

        # 尝试设置 stream_callback_var，使用 copy_context 以便在子线程中访问
        try:
            from contextvars import copy_context
            ctx = copy_context()
            def stream_wrapper(role: str, chunk: str):
                ctx.run(stream_cb, role, chunk)
            stream_callback_var.set(stream_wrapper)
        except Exception:
            stream_callback_var.set(stream_cb)

        # 获取当前轮次
        current_round = state.get("current_round", 1)
        app.call_from_thread(self._update_workflow_panel, "resumed", current_round, {})

        # 获取最大轮次
        try:
            settings = get_settings()
            max_rounds = settings.workflow.routing.max_rounds
        except Exception as e:
            app.call_from_thread(self._log_review, f"[red]配置加载错误: {e}[/]")
            app.call_from_thread(self._finish_review)
            return

        # 构建工作流
        try:
            app.call_from_thread(self._log_review, f"[bold]🔄 从第 {current_round} 轮继续评审...[/]\n")

            workflow = build_review_workflow(max_rounds)

            # 使用保存的状态继续运行工作流
            self._run_workflow(workflow, state, app, token_stats_map)

        except Exception as e:
            app.call_from_thread(self._log_review, f"[red]评审过程异常: {e}[/]")
            import traceback
            app.call_from_thread(self._log_review, f"[dim]{traceback.format_exc()}[/]")

        app.call_from_thread(self._finish_review)

    def _run_workflow(self, workflow, initial_state, app, token_stats_map):
        """运行工作流的通用方法"""
        final_state = None
        last_vote_result = None
        for state in workflow.stream(initial_state):
            if not self._review_running:
                app.call_from_thread(self._log_review, "[yellow]⏹ 评审已手动停止[/]")
                break

            # 检查工作流是否完成
            if state.get("workflow_status") == "已完成":
                app.call_from_thread(self._log_review, "\n[bold green]🏁 评审完成[/]")
                break

            if state.get("workflow_status") == "待人类决策":
                app.call_from_thread(self._log_review, "\n[bold yellow]⚠️ 需要人类介入[/]")
                break

            # 收集投票结果用于显示
            events = state.get("events", [])
            current_round = state.get("current_round", 1)
            vote_data = {}
            for event in events:
                if hasattr(event, 'vote_result') and event.vote_result and event.metadata.get("round") == current_round:
                    vote_data[event.actor] = {
                        "vote": event.vote_result,
                        "reasoning": ""
                    }
            
            # 统计投票
            if vote_data:
                yes_count = sum(1 for v in vote_data.values() if v["vote"] == "赞成")
                no_count = sum(1 for v in vote_data.values() if v["vote"] == "反对")
                abstain_count = sum(1 for v in vote_data.values() if v["vote"] == "弃权")
                
                vote_result = {
                    "yes": yes_count,
                    "no": no_count,
                    "abstain": abstain_count,
                    "role_data": vote_data
                }
                app.call_from_thread(self._update_vote_display, vote_result, len(vote_data))

            final_state = state

        # 如果正常完成，显示最终结果
        if final_state and self._review_running:
            viewpoint_pool = final_state.get("viewpoint_pool", [])
            resolved = len(final_state.get("resolved_viewpoints", []))

            if not viewpoint_pool:
                app.call_from_thread(self._log_review, "\n[bold green]✅ 所有观点已解决[/]")
                app.call_from_thread(self._log_review, f"   已解决观点数: {resolved}")

    def _log_review(self, msg: str):
        log = self.query_one("#review_log", RichLog)
        log.write(msg)

    def _stream_update(self, role: str, chunk: str):
        log = self.query_one("#review_log", RichLog)
        if chunk:
            role_colors = {
                "clerk": "cyan",
                "architect": "green",
                "innovator": "magenta",
                "security": "red",
                "cost_control": "yellow",
                "default": "white"
            }
            color = role_colors.get(role.lower(), role_colors["default"])
            log.write(f"[{color} bold][{role}][/] {chunk}")

    def _update_vote_display(self, vote_result, total):
        try:
            summary = f"赞成: [green]{vote_result.get('yes', 0)}[/] | 反对: [red]{vote_result.get('no', 0)}[/] | 弃权: [yellow]{vote_result.get('abstain', 0)}[/] / {total}"
            self._log_review(summary)

            voting_table = self.query_one("#voting_table", DataTable)
            if not voting_table.columns:
                voting_table.add_columns("角色", "投票", "理由")
            voting_table.clear()

            if "role_data" in vote_result:
                for role, data in vote_result["role_data"].items():
                    vote = data.get("vote", "")
                    # 支持中英文投票结果
                    if vote in ["赞成", "for", "for", "支持", "同意"]:
                        icon = "👍"
                    elif vote in ["反对", "against", "against", "不支持"]:
                        icon = "👎"
                    elif vote in ["弃权", "abstain", "abstain", "不发表意见"]:
                        icon = "🤔"
                    else:
                        icon = "❓"
                    reason = data.get("reasoning", "")
                    if len(reason) > 30:
                        reason = reason[:27] + "..."
                    voting_table.add_row(role, icon, reason)
        except Exception as e:
            self._log_review(f"[yellow]更新投票失败: {e}[/]")

    def _update_token_display(self, stats_map):
        """更新 Token 统计显示"""
        try:
            token_table = self.query_one("#token_table", DataTable)
            if not token_table.columns:
                token_table.add_columns("角色", "输入", "输出", "合计", "%")
            token_table.clear()

            # 累计总 token
            total_input = 0
            total_output = 0
            total_tokens = 0
            max_usage_percent = 0.0
            max_tokens = 0

            for role, stats in sorted(stats_map.items()):
                # 支持字典格式和对象格式
                if isinstance(stats, dict):
                    input_tokens = stats.get("input_tokens", 0)
                    output_tokens = stats.get("output_tokens", 0)
                    role_total = stats.get("total_tokens", 0)
                    usage_percent = stats.get("usage_percent", 0.0)
                    role_max = stats.get("max_tokens", 0)
                else:
                    # 对象格式（如 TokenStats）
                    input_tokens = getattr(stats, 'input_tokens', 0)
                    output_tokens = getattr(stats, 'output_tokens', 0)
                    role_total = getattr(stats, 'total_tokens', 0)
                    usage_percent = getattr(stats, 'usage_percent', 0.0)
                    role_max = getattr(stats, 'max_tokens', 0)

                total_input += input_tokens
                total_output += output_tokens
                total_tokens += role_total
                max_usage_percent = max(max_usage_percent, usage_percent)
                max_tokens = max(max_tokens, role_max)

                token_table.add_row(
                    str(role),
                    f"{input_tokens:,}",
                    f"{output_tokens:,}",
                    f"{role_total:,}",
                    f"{usage_percent:.1f}%" if usage_percent else "0%",
                )

            # 添加总计行
            total_usage_percent = (total_tokens / max_tokens * 100) if max_tokens > 0 else 0
            token_table.add_row(
                "━━ 总计 ━━",
                f"{total_input:,}",
                f"{total_output:,}",
                f"{total_tokens:,}",
                f"{total_usage_percent:.1f}%",
            )
        except Exception as e:
            self._log_review(f"[yellow]更新Token统计失败: {e}[/]")

    def _update_workflow_panel(self, stage: str, round_num: int, role_data: dict):
        """更新工作流状态面板"""
        try:
            workflow_panel = self.query_one("#workflow_panel", WorkflowStatusPanel)
            workflow_panel.update_stage(stage)
            workflow_panel.update_round(round_num, 10)
        except Exception:
            pass

    def _update_workflow_role(self, role: str, status: str):
        """更新工作流中的角色状态"""
        try:
            workflow_panel = self.query_one("#workflow_panel", WorkflowStatusPanel)
            workflow_panel.update_role_status(role, status)
        except Exception:
            pass

    def _finish_review(self):
        """评审结束处理"""
        try:
            start_btn = self.query_one("#start_review_btn", Button)
            start_btn.disabled = False
            # 检查是否有保存的状态，恢复按钮
            try:
                _, saved_state, _ = get_latest_saved_state()
                resume_btn = self.query_one("#resume_review_btn", Button)
                resume_btn.disabled = not saved_state
            except Exception:
                pass
            status = self.query_one("#review_status", Static)
            status.update("[green]完成[/]")
        except Exception:
            pass



def run_textual_app():
    app = EvolveRFCApp()
    app.run()


if __name__ == "__main__":
    run_textual_app()
