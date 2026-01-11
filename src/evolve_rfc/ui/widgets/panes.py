"""功能页面组件

提供完整的功能页面：
- ReviewPane: RFC 评审页面
- NightlyPane: 夜间守护页面
- SettingsPane: 系统设置页面
"""

from pathlib import Path
from typing import Any
from textual import on, work
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Input, RichLog, Static, Tree
from textual.widgets.tree import TreeNode

from evolve_rfc.settings import get_settings
from evolve_rfc.shared.debate import run_parallel_review, analyze_votes, check_approval
from evolve_rfc.ui.textual_ui import TokenStats
from .panels import (
    RoleStatusPanel,
    VotingResultPanel,
    TokenDataPanel,
)


class ReviewPane(Container):
    """RFC 评审页"""

    CSS = """
    ReviewPane {
        height: 100%;
        width: 100%;
    }
    """

    def compose(self):
        with Horizontal(id="review-controls"):
            yield Label("📄 RFC 路径:", id="path-label")
            yield Input(placeholder="rfcs/example.md", value="rfcs/example.md", id="rfc_path")
            yield Button("🚀 开始评审", id="start_review_btn", variant="primary")
            yield Static("就绪", id="review_status")

        with Horizontal(id="review-main"):
            # 左侧日志流
            with Vertical(id="log-area"):
                yield Label("📜 实时日志", classes="panel-title")
                yield RichLog(id="review_log", markup=True, wrap=True, max_lines=5000)

            # 右侧面板区
            with VerticalScroll(id="info-area"):
                yield RoleStatusPanel(id="role_panel")
                yield VotingResultPanel(id="vote_panel")
                yield TokenDataPanel(id="token_panel")

    @on(Button.Pressed, "#start_review_btn")
    def on_start(self):
        path_input = self.query_one("#rfc_path", Input)
        path = path_input.value

        if not path:
            self.query_one("#review_log", RichLog).write("[red]❌ 请输入路径[/]")
            return

        p = Path(path)
        if not p.exists():
            self.query_one("#review_log", RichLog).write(f"[red]❌ 文件不存在: {path} (当前目录: {Path.cwd()})[/]")
            return

        self.query_one("#start_review_btn", Button).disabled = True
        self.query_one("#review_status", Static).update("[yellow]运行中...[/]")
        self.run_review(str(p))

    @work(thread=True)
    def run_review(self, path: str) -> None:
        """后台运行评审流程"""
        app = self.app

        try:
            settings = get_settings()
            max_rounds = settings.workflow.routing.max_rounds
            yes_votes_needed = int(settings.workflow.thresholds.consensus_quorum)
            if hasattr(settings, "nightly") and hasattr(settings.nightly, "creative_proposal"):
                yes_votes_needed = settings.nightly.creative_proposal.yes_votes_needed
            no_votes_limit = 1
        except Exception as e:
            app.call_from_thread(self._log, f"[red]配置加载错误: {e}[/]")
            app.call_from_thread(self._finish_review)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                rfc_content = f.read()
        except Exception as e:
            app.call_from_thread(self._log, f"[red]读取出错: {e}[/]")
            app.call_from_thread(self._finish_review)
            return

        all_results = []
        token_stats_map = {}

        for round_num in range(1, max_rounds + 1):
            app.call_from_thread(self._log, f"\n[bold cyan]=== 第 {round_num} 轮评审 ===[/]\n")

            def stream_cb(role: str, chunk: str):
                app.call_from_thread(self._stream_update, role, chunk)

            def token_cb(data: dict):
                role = data.get("role", "unknown")
                if isinstance(data, dict):
                    try:
                        stats = TokenStats(**data)
                    except TypeError:
                        stats = TokenStats(
                            role=data.get("role", role),
                            input_tokens=data.get("input_tokens", 0),
                            output_tokens=data.get("output_tokens", 0),
                            total_tokens=data.get("total_tokens", 0),
                            remaining=data.get("remaining", 0),
                            max_tokens=data.get("max_tokens", 0),
                            usage_percent=data.get("usage_percent", 0.0)
                        )
                else:
                    stats = data
                token_stats_map[role] = stats
                app.call_from_thread(self._update_tokens, token_stats_map)

            try:
                results = run_parallel_review(
                    content=rfc_content,
                    current_round=round_num,
                    stream_callback=stream_cb,
                    token_callback=token_cb,
                )
            except Exception as e:
                app.call_from_thread(self._log, f"[red]评审过程异常: {e}[/]")
                import traceback
                app.call_from_thread(self._log, f"[dim]{traceback.format_exc()}[/]")
                break

            all_results.extend(results)

            vote_result = analyze_votes(results)
            app.call_from_thread(self._update_votes, vote_result, len(results))

            round_roles_data = []
            for r in results:
                name = getattr(r, "name", "AI")
                content = getattr(r, "content", str(r))
                round_roles_data.append({
                    "name": name,
                    "done": True,
                    "viewpoint": content,
                    "vote": "?"
                })
            app.call_from_thread(self._update_roles, round_roles_data)

            check = check_approval(
                vote_result=vote_result,
                max_rounds=max_rounds,
                current_round=round_num,
                yes_votes_needed=yes_votes_needed if isinstance(yes_votes_needed, (int, float)) else 3,
                no_votes_limit=no_votes_limit
            )

            if check["finished"]:
                result_str = "通过" if check["approved"] else "否决"
                color = "green" if check["approved"] else "red"
                app.call_from_thread(self._log, f"\n[bold {color}]🏁 最终结果: {result_str}[/]")
                break

        app.call_from_thread(self._finish_review)

    def _log(self, msg: str):
        self.query_one("#review_log", RichLog).write(msg)

    def _stream_update(self, role: str, chunk: str):
        log = self.query_one("#review_log", RichLog)
        if chunk:
            log.write(f"[{role}] {chunk}")

    def _update_tokens(self, stats_map):
        self.query_one("#token_panel", TokenDataPanel).update_tokens(stats_map)

    def _update_votes(self, vote_result, total_approx):
        self.query_one("#vote_panel", VotingResultPanel).update_results(vote_result, total_approx)

    def _update_roles(self, roles_data):
        self.query_one("#role_panel", RoleStatusPanel).update_roles(roles_data)

    def _finish_review(self):
        self.query_one("#start_review_btn", Button).disabled = False
        self.query_one("#review_status", Static).update("[green]完成[/]")


class NightlyPane(Container):
    """夜间守护页"""

    CSS = """
    NightlyPane {
        height: 100%;
        width: 100%;
    }
    """

    def compose(self):
        with Vertical():
            yield Label("🌙 夜间守护进程", classes="panel-title")
            yield Static("自动运行夜间评审任务，生成创意提案或进行代码审计。", classes="desc")

            with Horizontal(id="nightly-controls"):
                yield Button("▶ 启动守护", id="start_nightly", variant="warning")
                yield Button("⏹ 停止", id="stop_nightly", variant="error", disabled=True)
                yield Static("状态: 停止", id="nightly_status")

            yield RichLog(id="nightly_log", markup=True, highlight=True)

    @on(Button.Pressed, "#start_nightly")
    def start_nightly(self):
        self.query_one("#start_nightly", Button).disabled = True
        self.query_one("#stop_nightly", Button).disabled = False
        self.query_one("#nightly_status", Static).update("状态: [bold green]运行中[/]")
        self.query_one("#nightly_log", RichLog).write("[yellow]正在启动夜间守护进程...[/]")

        self.run_nightly_process()

    @work(thread=True)
    def run_nightly_process(self):
        try:
            from evolve_rfc.utils.config import load_nightly_config
            from evolve_rfc.nightly.modes import run_mode

            app = self.app

            config_path = "config/nightly.yaml"
            if Path(config_path).exists():
                full_config = load_nightly_config(config_path)
                mode_weights = full_config.get("nightly", {}).get("mode_weights", {})
                app.call_from_thread(self._log, f"加载配置成功，权重: {mode_weights}")

                app.call_from_thread(self._log, "正在执行夜间任务 (单次模式)...")

                output_dir = "nightly_output"
                Path(output_dir).mkdir(parents=True, exist_ok=True)

                selected_mode = "audit"
                if mode_weights:
                    selected_mode = list(mode_weights.keys())[0]

                run_mode(selected_mode, full_config, output_dir)

                app.call_from_thread(self._log, "✅ 任务执行完毕")
            else:
                app.call_from_thread(self._log, f"[red]配置未找到: {config_path}[/]")

        except Exception as e:
            self.app.call_from_thread(self._log, f"[red]执行错误: {e}[/]")
            import traceback
            self.app.call_from_thread(self._log, f"[dim]{traceback.format_exc()}[/]")

        self.app.call_from_thread(self._finish_nightly)

    def _log(self, msg):
        self.query_one("#nightly_log", RichLog).write(msg)

    def _finish_nightly(self):
        self.query_one("#start_nightly", Button).disabled = False
        self.query_one("#stop_nightly", Button).disabled = True
        self.query_one("#nightly_status", Static).update("状态: 停止")

    @on(Button.Pressed, "#stop_nightly")
    def stop_nightly(self):
        self.query_one("#nightly_log", RichLog).write("[red]正在请求停止(请等待任务完成)...[/]")


class SettingsPane(Container):
    """设置页"""

    CSS = """
    SettingsPane {
        height: 100%;
        width: 100%;
    }
    """

    def compose(self):
        yield Label("⚙️ 系统设置", classes="panel-title")
        yield Tree("Current Configuration", id="config_tree")

    def on_mount(self):
        self.load_config()

    def load_config(self):
        tree = self.query_one("#config_tree", Tree)
        tree.root.expand()

        try:
            settings = get_settings()
            if hasattr(settings, "model_dump"):
                data = settings.model_dump()
            elif hasattr(settings, "__dict__"):
                data = settings.__dict__
            else:
                data = {"error": "Unknown settings object"}

            self.add_node(tree.root, data)
        except Exception as e:
            tree.root.add(f"Error loading settings: {e}")

    def add_node(self, node: TreeNode, data: Any):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    child = node.add(f"[bold cyan]{key}[/]", expand=False)
                    self.add_node(child, value)
                else:
                    node.add(f"[cyan]{key}[/]: [yellow]{value}[/]")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                child = node.add(f"[{i}]", expand=False)
                self.add_node(child, item)
        else:
            node.add(str(data))
