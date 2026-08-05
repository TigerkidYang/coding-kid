"""A simplified Codex-style full-screen terminal interface."""

from __future__ import annotations

import time
import inspect
from collections.abc import Callable
from typing import Any

from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.widgets import Markdown, Static, TextArea

from coding_kid.agent import current_instructions, run_turn
from coding_kid.agents import AgentEvent, AgentManager
from coding_kid.background_tasks import BackgroundTaskManager, TaskEvent
from coding_kid.capabilities import CapabilityRuntime
from coding_kid.compaction import compact_context
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextManager
from coding_kid.events import (
    AssistantMessageCompleted,
    AssistantStreamReset,
    AssistantTextDelta,
    CancellationToken,
    CompactionCompleted,
    CompactionStarted,
    ContextWarning,
    EventSink,
    InputConsumed,
    InputQueued,
    InputRejected,
    TodoUpdated,
    ToolCompleted,
    ToolStarted,
    TurnCompleted,
    TurnCancelled,
    TurnEvent,
    TurnFailed,
    TurnInterrupted,
)
from coding_kid.memory import MemoryManager, MemorySyncResult
from coding_kid.provider import generate, generate_streaming
from coding_kid.sessions import SessionError, SessionHandle
from coding_kid.skills import SkillTurnState, explicit_skill_names
from coding_kid.tools import TodoState, build_tool_registry
from coding_kid.turn_control import TurnController

Provider = Callable[..., Any]


class Composer(TextArea):
    """A small multiline composer with Codex-style submit behavior."""

    BINDINGS = [
        *TextArea.BINDINGS,
        Binding("enter", "submit", show=False, priority=True),
        Binding("shift+enter", "newline", show=False, priority=True),
    ]

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def action_submit(self) -> None:
        if self.read_only:
            return
        text = self.text.strip()
        if not text:
            return
        self.load_text("")
        self.post_message(self.Submitted(text))

    def action_newline(self) -> None:
        if not self.read_only:
            self.insert("\n")


class AssistantCell(Horizontal):
    """One mutable streaming message that becomes source-backed on completion."""

    def __init__(self, source: str = "") -> None:
        self.markdown = Markdown(source, classes="assistant-markdown")
        super().__init__(
            Static("[dim]•[/]", classes="assistant-bullet"),
            self.markdown,
            classes="assistant-cell",
        )
        self.source_text = source

    def replace_source(self, source: str) -> None:
        self.source_text = source
        self.markdown.update(source)


class CodingKidApp(App[None]):
    """Render one session while the synchronous agent runs in a worker thread."""

    TITLE = "Coding Kid"
    BINDINGS = [
        Binding("escape", "interrupt", show=False, priority=True),
        Binding("ctrl+c", "cancel_or_quit", show=False, priority=True),
    ]
    CSS = """
    Screen {
        layout: vertical;
    }

    #transcript {
        height: 1fr;
        padding: 1 2 0 2;
        scrollbar-size: 1 1;
    }

    .session-card {
        width: 100%;
        max-width: 60;
        border: round $secondary;
        padding: 1 2;
        margin-bottom: 1;
    }

    .help-cell, .tool-cell, .context-cell, .notice-cell, .error-cell,
    .todo-cell, .assistant-cell {
        width: 100%;
        margin-bottom: 1;
    }

    .user-cell {
        width: 100%;
        padding: 1 1;
        margin-bottom: 1;
        background: $surface;
    }

    .assistant-cell {
        layout: horizontal;
        height: auto;
    }

    .assistant-bullet {
        width: 2;
        height: 1;
    }

    .assistant-markdown {
        width: 1fr;
        height: auto;
    }

    .error-cell {
        color: $error;
    }

    #status {
        height: 1;
        margin: 0 2;
        color: $text-muted;
        display: none;
    }

    #composer {
        height: auto;
        min-height: 3;
        max-height: 7;
        margin: 0 2;
        border: round $secondary;
    }

    #footer {
        height: 1;
        margin: 0 2;
        color: $text-muted;
    }

    #footer-left {
        width: 1fr;
    }

    #footer-right {
        width: auto;
        text-align: right;
    }
    """

    def __init__(
        self,
        session_context: SessionContext,
        manager: ContextManager,
        *,
        provider: Provider = generate,
        streaming_provider: Provider = generate_streaming,
        session_handle: SessionHandle | None = None,
        memory_manager: MemoryManager | None = None,
        capability_runtime: CapabilityRuntime | None = None,
        background_tasks: BackgroundTaskManager | None = None,
        todo_state: TodoState | None = None,
        agent_manager: AgentManager | None = None,
    ) -> None:
        super().__init__()
        self.session_context = session_context
        self.manager = manager
        self.provider = provider
        self.streaming_provider = streaming_provider
        self.session_handle = session_handle
        self.memory_manager = memory_manager
        self.capability_runtime = capability_runtime
        self.background_tasks = background_tasks or BackgroundTaskManager()
        self.todo_state = todo_state or TodoState(
            session_handle.todos if session_handle is not None else None
        )
        self.agent_manager = agent_manager or AgentManager(
            session_context,
            manager.budget,
            capability_runtime=capability_runtime,
        )
        self._owns_agent_manager = agent_manager is None
        self._owns_background_tasks = background_tasks is None
        self.active_turn = False
        self.cancellation_token: CancellationToken | None = None
        self._active_assistant: AssistantCell | None = None
        self._pending_deltas: list[str] = []
        self._status_label = "Working"
        self._status_started = 0.0
        self.turn_controller = TurnController()

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="transcript")
        yield Static(id="status")
        yield Composer(
            id="composer",
            placeholder="Ask Coding Kid to do anything",
            soft_wrap=True,
            show_line_numbers=False,
            compact=True,
        )
        yield Horizontal(
            Static(id="footer-left"),
            Static(id="footer-right"),
            id="footer",
        )

    def on_mount(self) -> None:
        self._mount_session_header()
        self._refresh_footer()
        self.query_one(Composer).focus()
        self.set_interval(0.05, self._flush_deltas)
        self.set_interval(1.0, self._refresh_status)
        self.set_interval(0.1, self._drain_task_events)
        self.set_interval(0.1, self._drain_agent_events)
        if self.memory_manager is not None and self.memory_manager.mode == "auto":
            self.call_after_refresh(self._start_memory_sync, False)

    def _mount_session_header(self) -> None:
        model = escape(self.session_context.model)
        cwd = escape(str(self.session_context.cwd))
        self._append_cell(
            Static(
                "[dim]>_ [/][b]Coding Kid[/] [dim](v10)[/]\n\n"
                f"[dim]model:     [/]{model}\n"
                f"[dim]directory: [/]{cwd}\n"
                f"[dim]session:   [/]{self._session_label()}",
                classes="session-card",
            )
        )
        self._append_cell(
            Static(
                "[dim]  Describe a task, or use /agents, /tasks, /session, /sessions, "
                "/context, /compact, or /exit.[/]",
                classes="help-cell",
            )
        )
        if self.capability_runtime is not None:
            self._append_cell(
                Static(
                    f"[dim]• {escape(self.capability_runtime.summary())}[/]",
                    classes="context-cell",
                )
            )

    def _append_cell(self, widget: Static | Markdown | Horizontal) -> None:
        transcript = self.query_one("#transcript", VerticalScroll)
        transcript.mount(widget)
        self.call_after_refresh(transcript.scroll_end, animate=False)

    def on_composer_submitted(self, message: Composer.Submitted) -> None:
        text = message.text
        if text in {"/exit", "/quit"}:
            self.exit()
            return
        if text == "/context":
            self._show_context()
            return
        if text == "/tasks":
            self._show_background_tasks()
            return
        if text == "/agents":
            self._show_agents()
            return
        if text.startswith("/agent stop "):
            self._start_agent_stop(text.removeprefix("/agent stop ").strip())
            return
        if text.startswith("/task stop "):
            self._start_task_stop(text.removeprefix("/task stop ").strip())
            return
        if text == "/capabilities":
            self._show_capabilities()
            return
        if text == "/session":
            self._show_session()
            return
        if text == "/session save":
            self._retry_session_save()
            return
        if text == "/sessions":
            self._show_sessions()
            return
        if text == "/memory":
            self._show_memory_status()
            return
        if text.startswith("/memory search "):
            self._show_memory_search(text.removeprefix("/memory search "))
            return
        if text == "/memory sync":
            self._start_memory_sync(True)
            return
        if text.startswith("/remember "):
            self._remember(text.removeprefix("/remember "))
            return
        if text.startswith("/forget "):
            self._forget(text.removeprefix("/forget "))
            return
        if self.session_handle is not None and self.session_handle.dirty:
            self._show_persistence_error(
                "Save the pending transition with /session save before continuing."
            )
            return
        if text == "/compact":
            self._start_manual_compaction()
            return
        if self.active_turn:
            if self.turn_controller.steer(text):
                self.handle_turn_event(
                    InputQueued(text, self.turn_controller.pending_count)
                )
            else:
                self.query_one(Composer).load_text(text)
                self.handle_turn_event(
                    InputRejected(
                        "Steer queue is full; input was kept in the composer."
                    )
                )
            return

        self._append_cell(Static(f"[b dim]›[/] {escape(text)}", classes="user-cell"))
        self._begin_activity("Working")
        self.run_worker(
            lambda: self._run_turn(text),
            name="agent-turn",
            group="agent",
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def _run_turn(self, user_text: str) -> None:
        pending_texts = [user_text]
        persistence_kind = "state_committed"
        while pending_texts:
            token = self.cancellation_token
            combined_text = "\n".join(pending_texts)
            for pending_text in pending_texts:
                self.manager.conversation.append_user(pending_text)
            pending_texts = []
            persistence_kind = "state_committed"
            should_continue = False
            step_outcome = self._run_controlled_step(combined_text, token)
            if step_outcome == "failed":
                persistence_kind = "turn_failed"
            if token is not None and token.cancelled:
                persistence_kind = (
                    "turn_steered" if token.reason == "steered" else "turn_interrupted"
                )
                if token.reason == "steered":
                    queued = self.turn_controller.take_pending()
                    if queued:
                        pending_texts = [item.text for item in queued]
                        for item in queued:
                            self.call_from_thread(
                                self.handle_turn_event,
                                InputConsumed(item.text),
                            )
                        self.cancellation_token = self.turn_controller.next_step_token()
                        should_continue = True
            if self.session_handle is not None:
                self.session_handle.todos = self.todo_state.items
                try:
                    self.session_handle.commit_state(kind=persistence_kind)
                except BaseException as error:
                    self.call_from_thread(self._show_persistence_error, str(error))
                    should_continue = False
            if not should_continue:
                break
        self.call_from_thread(self._finish_activity)

    def _run_controlled_step(
        self, user_text: str, token: CancellationToken | None
    ) -> str:
        request_context: list[Any] = []
        recalled_ids: tuple[str, ...] = ()
        if self.memory_manager is not None:
            request_context, recalled_ids = self.memory_manager.recall_context(
                user_text
            )
        skill_state: SkillTurnState | None = None
        registry = build_tool_registry(
            self.background_tasks,
            token,
            self.todo_state,
            self.agent_manager,
        )
        overlays: tuple[str, ...] = ()
        if self.capability_runtime is not None:
            skill_state = SkillTurnState(self.capability_runtime.snapshot.skills)
            for skill_name in explicit_skill_names(
                user_text, self.capability_runtime.snapshot.skills
            ):
                request_context.append(
                    {
                        "role": "user",
                        "content": self.capability_runtime.load_skill(
                            skill_state, skill_name, explicit=True
                        ),
                    }
                )
            registry = self.capability_runtime.registry_for_turn(
                skill_state,
                token,
                base_registry=registry,
            )
            metadata = self.capability_runtime.skill_metadata()
            overlays = (metadata,) if metadata else ()
        try:
            turn_options = {
                "on_context": None,
                "session_context": self.session_context,
                "stream_provider": self.streaming_provider,
                "event_sink": self._thread_event_sink(),
                "cancellation_token": token,
                "request_context": request_context,
                "on_memory_citations": (
                    lambda cited: (
                        self.memory_manager.record_usage(set(cited) & set(recalled_ids))
                        if self.memory_manager is not None
                        else None
                    )
                ),
                "tool_registry": registry,
                "instruction_overlays": overlays,
                "todo_state": self.todo_state,
                "agent_manager": self.agent_manager,
            }
            if "background_tasks" in inspect.signature(run_turn).parameters:
                turn_options["background_tasks"] = self.background_tasks
            run_turn(
                self.manager,
                self.provider,
                **turn_options,
            )
        except TurnCancelled:
            return "interrupted"
        except BaseException:
            return "failed"
        return "completed"

    def _thread_event_sink(self) -> EventSink:
        return lambda event: self.call_from_thread(self.handle_turn_event, event)

    def handle_turn_event(self, event: TurnEvent) -> None:
        if isinstance(event, AssistantTextDelta):
            self._pending_deltas.append(event.delta)
        elif isinstance(event, AssistantStreamReset):
            self._discard_active_assistant()
        elif isinstance(event, AssistantMessageCompleted):
            self._complete_assistant(event.text)
        elif isinstance(event, ToolStarted):
            self._set_status(_tool_status(event.name, event.arguments))
        elif isinstance(event, ToolCompleted):
            self._show_tool(event)
            self._set_status("Working")
        elif isinstance(event, TodoUpdated):
            self._show_todo(event)
        elif isinstance(event, CompactionStarted):
            self._set_status("Compacting conversation")
        elif isinstance(event, CompactionCompleted):
            self._show_compaction(event)
            self._refresh_footer()
            self._set_status("Working")
        elif isinstance(event, ContextWarning):
            self._append_cell(
                Static(f"[yellow]▲ {escape(event.message)}[/]", classes="notice-cell")
            )
            if self.active_turn:
                self._set_status("Working")
        elif isinstance(event, InputQueued):
            self._append_cell(
                Static(f"[b cyan]↪[/] {escape(event.text)}", classes="user-cell")
            )
            self._set_status(f"Steering ({event.position} queued)")
        elif isinstance(event, InputConsumed):
            self._set_status("Applying queued input")
        elif isinstance(event, InputRejected):
            self._append_cell(
                Static(
                    f"[yellow]▲ {escape(event.message)}[/]",
                    classes="notice-cell",
                )
            )
        elif isinstance(event, TurnCompleted):
            self._refresh_footer()
        elif isinstance(event, TurnInterrupted):
            self._discard_active_assistant()
            steered = "steered" in event.message.casefold()
            self._append_cell(
                Static(
                    (
                        "[cyan]↪ Current step stopped; applying queued input.[/]"
                        if steered
                        else "[yellow]■ Turn interrupted; completed work was retained.[/]"
                    ),
                    classes="notice-cell",
                )
            )
        elif isinstance(event, TurnFailed):
            self._discard_active_assistant()
            self._append_cell(
                Static(
                    f"■ {escape(event.message)}\n[dim]  Conversation, context, and "
                    "completed work retained.[/]",
                    classes="error-cell",
                )
            )

    def _flush_deltas(self) -> None:
        if not self._pending_deltas:
            return
        if self._active_assistant is None:
            source = "".join(self._pending_deltas)
            self._pending_deltas.clear()
            self._active_assistant = AssistantCell(source)
            self._append_cell(self._active_assistant)
            return
        source = self._active_assistant.source_text + "".join(self._pending_deltas)
        self._pending_deltas.clear()
        self._active_assistant.replace_source(source)

    def _complete_assistant(self, final_text: str) -> None:
        self._flush_deltas()
        if not final_text.strip():
            return
        if self._active_assistant is None:
            self._active_assistant = AssistantCell(final_text)
            self._append_cell(self._active_assistant)
        elif self._active_assistant.source_text != final_text:
            self._active_assistant.replace_source(final_text)
        self._active_assistant = None

    def _discard_active_assistant(self) -> None:
        self._pending_deltas.clear()
        if self._active_assistant is not None:
            self._active_assistant.remove()
            self._active_assistant = None

    def _show_tool(self, event: ToolCompleted) -> None:
        if event.name == "todo":
            return
        if event.failed:
            self._append_cell(
                Static(
                    f"■ {escape(_tool_description(event.name, event.arguments))}\n"
                    f"  {escape(event.result)}",
                    classes="error-cell",
                )
            )
            return
        self._append_cell(
            Static(
                Text(_tool_description(event.name, event.arguments)),
                classes="tool-cell",
                markup=False,
            )
        )

    def _show_todo(self, event: TodoUpdated) -> None:
        content = Text()
        content.append("• Updated Plan\n", style="bold")
        if not event.items:
            content.append("  └ (no steps provided)", style="dim italic")
        for index, item in enumerate(event.items):
            prefix = "  └ " if index == 0 else "    "
            if item.status == "completed":
                content.append(f"{prefix}✔ {item.content}\n", style="dim strike")
            elif item.status == "in_progress":
                content.append(f"{prefix}□ {item.content}\n", style="bold cyan")
            else:
                content.append(f"{prefix}□ {item.content}\n", style="dim")
        self._append_cell(Static(content, classes="todo-cell", markup=False))

    def _show_compaction(self, event: CompactionCompleted) -> None:
        self._append_cell(
            Static(
                f"[dim]• Compacted context ({event.before_tokens:,} → "
                f"{event.after_tokens:,} estimated tokens)[/]",
                classes="context-cell",
            )
        )

    def _show_context(self) -> None:
        base_registry = build_tool_registry(
            self.background_tasks,
            todo_state=self.todo_state,
            agent_manager=self.agent_manager,
        )
        definitions = base_registry.definitions()
        task_summary = self.background_tasks.prompt_summary()
        overlays: tuple[str, ...] = (task_summary,) if task_summary else ()
        if self.capability_runtime is not None:
            definitions = self.capability_runtime.registry_for_turn(
                SkillTurnState(self.capability_runtime.snapshot.skills),
                base_registry=base_registry,
            ).definitions()
            metadata = self.capability_runtime.skill_metadata()
            overlays = (*overlays, *((metadata,) if metadata else ()))
        status = self.manager.status_text(
            current_instructions(self.session_context, overlays, self.todo_state),
            definitions,
        )
        self._append_cell(
            Static(
                f"[b]• Context[/]\n  {escape(status).replace(chr(10), chr(10) + '  ')}",
                classes="context-cell",
            )
        )

    def _show_capabilities(self) -> None:
        status = (
            self.capability_runtime.status_text()
            if self.capability_runtime is not None
            else "Pluggable capabilities are not active."
        )
        self._append_cell(
            Static(
                f"[b]• Capabilities[/]\n  "
                f"{escape(status).replace(chr(10), chr(10) + '  ')}",
                classes="context-cell",
            )
        )

    def _session_label(self) -> str:
        if self.session_handle is None:
            return "ephemeral"
        return f"{self.session_handle.info.session_id[:8]} ({self.session_handle.info.status})"

    def _show_session(self) -> None:
        self._append_cell(
            Static(
                f"[b]• Session[/]\n  {escape(self._session_label())}",
                classes="context-cell",
            )
        )

    def _retry_session_save(self) -> None:
        if self.session_handle is None:
            self._show_session()
            return
        try:
            self.session_handle.retry_save()
        except Exception as error:
            self._show_persistence_error(str(error))
            return
        self._append_cell(
            Static("[dim]• Session state is durable.[/]", classes="context-cell")
        )

    def _show_sessions(self) -> None:
        if self.session_handle is None:
            rendered = "Session persistence is not active."
        else:
            items = self.session_handle.store.list_sessions()
            rendered = (
                "\n".join(
                    f"{item.session_id[:8]}  {item.status}  {item.title}"
                    for item in items
                )
                or "No sessions for this project."
            )
        self._append_cell(
            Static(
                f"[b]• Sessions[/]\n  "
                f"{escape(rendered).replace(chr(10), chr(10) + '  ')}",
                classes="context-cell",
            )
        )

    def _show_persistence_error(self, message: str) -> None:
        self._append_cell(
            Static(
                "■ Persistence failed; the completed turn remains in memory but "
                f"is not durable.\n  {escape(message)}",
                classes="error-cell",
            )
        )

    def _show_memory_status(self) -> None:
        rendered = (
            self.memory_manager.status_text()
            if self.memory_manager is not None
            else "Long-term memory is not active."
        )
        self._append_cell(
            Static(f"[b]• Memory[/]\n  {escape(rendered)}", classes="context-cell")
        )

    def _show_memory_search(self, query: str) -> None:
        if self.memory_manager is None:
            rendered = "Long-term memory is not active."
        else:
            entries = self.memory_manager.search(query)
            rendered = (
                "\n".join(
                    f"{item.memory_id[:8]}  {item.scope}/{item.type}  {item.title}"
                    for item in entries
                )
                or "No matching memories."
            )
        self._append_cell(
            Static(
                f"[b]• Memory Search[/]\n  "
                f"{escape(rendered).replace(chr(10), chr(10) + '  ')}",
                classes="context-cell",
            )
        )

    def _remember(self, content: str) -> None:
        if self.memory_manager is None:
            self._show_memory_status()
            return
        global_scope = content.startswith("--global ")
        if global_scope:
            content = content.removeprefix("--global ")
        try:
            entry = self.memory_manager.add(content, global_scope=global_scope)
        except SessionError as error:
            self._show_persistence_error(str(error))
            return
        self._append_cell(
            Static(
                f"[dim]• Remembered {entry.memory_id[:8]} ({entry.scope})[/]",
                classes="context-cell",
            )
        )

    def _forget(self, memory_id: str) -> None:
        if self.memory_manager is None:
            self._show_memory_status()
            return
        try:
            entry = self.memory_manager.forget(memory_id)
        except SessionError as error:
            self._show_persistence_error(str(error))
            return
        self._append_cell(
            Static(
                f"[dim]• Forgot memory {entry.memory_id[:8]}[/]",
                classes="context-cell",
            )
        )

    def _start_memory_sync(self, force: bool = True) -> None:
        if (
            self.active_turn
            or self.memory_manager is None
            or self.session_handle is None
        ):
            return
        self._begin_activity("Updating long-term memory")
        self.run_worker(
            lambda: self._run_memory_sync(force),
            name="memory-sync",
            group="agent",
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def _run_memory_sync(self, force: bool) -> None:
        assert self.memory_manager is not None
        assert self.session_handle is not None
        result = self.memory_manager.sync(
            self.provider,
            current_session_id=self.session_handle.info.session_id,
            force=force,
        )
        self.call_from_thread(self._show_memory_sync, result)
        self.call_from_thread(self._finish_activity)

    def _show_memory_sync(self, result: MemorySyncResult) -> None:
        if result.error:
            rendered = f"Memory update failed: {result.error}"
            classes = "error-cell"
        else:
            rendered = (
                f"Memory updated: {result.extracted_sessions} session(s) extracted, "
                f"{result.consolidated_memories} item(s) consolidated."
            )
            classes = "context-cell"
        self._append_cell(Static(f"[dim]• {escape(rendered)}[/]", classes=classes))

    def _start_manual_compaction(self) -> None:
        if self.active_turn:
            return
        self._begin_activity("Compacting conversation")
        self.run_worker(
            self._run_manual_compaction,
            name="manual-compaction",
            group="agent",
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def _run_manual_compaction(self) -> None:
        snapshot = self.manager.clone()
        base_registry = build_tool_registry(
            self.background_tasks,
            self.cancellation_token,
            self.todo_state,
            self.agent_manager,
        )
        definitions = base_registry.definitions()
        task_summary = self.background_tasks.prompt_summary()
        overlays: tuple[str, ...] = (task_summary,) if task_summary else ()
        if self.capability_runtime is not None:
            definitions = self.capability_runtime.registry_for_turn(
                SkillTurnState(self.capability_runtime.snapshot.skills),
                self.cancellation_token,
                base_registry=base_registry,
            ).definitions()
            metadata = self.capability_runtime.skill_metadata()
            overlays = (*overlays, *((metadata,) if metadata else ()))
        try:
            compact_context(
                self.manager,
                self.provider,
                instructions=current_instructions(
                    self.session_context, overlays, self.todo_state
                ),
                tools=definitions,
                trigger="manual",
                event_sink=self._thread_event_sink(),
                cancellation_token=self.cancellation_token,
            )
        except TurnCancelled as error:
            self.manager.restore(snapshot)
            self.call_from_thread(
                self.handle_turn_event,
                TurnInterrupted(str(error)),
            )
        except BaseException as error:
            self.manager.restore(snapshot)
            self.call_from_thread(
                self.handle_turn_event,
                ContextWarning(f"Compaction failed: {error}"),
            )
        else:
            if self.session_handle is not None:
                self.session_handle.todos = self.todo_state.items
                try:
                    self.session_handle.commit_state(kind="context_committed")
                except BaseException as error:
                    self.call_from_thread(self._show_persistence_error, str(error))
        finally:
            self.call_from_thread(self._finish_activity)

    def _begin_activity(self, label: str) -> None:
        self.active_turn = True
        self.cancellation_token = self.turn_controller.begin()
        composer = self.query_one(Composer)
        composer.read_only = False
        self._status_started = time.monotonic()
        self._set_status(label)

    def _finish_activity(self) -> None:
        self.active_turn = False
        self.cancellation_token = None
        self.turn_controller.finish()
        composer = self.query_one(Composer)
        composer.read_only = False
        composer.focus()
        status = self.query_one("#status", Static)
        status.display = False
        self._refresh_footer()

    def _set_status(self, label: str) -> None:
        self._status_label = label
        self._refresh_status()

    def _refresh_status(self) -> None:
        if not self.active_turn:
            return
        elapsed = max(0, int(time.monotonic() - self._status_started))
        status = self.query_one("#status", Static)
        status.display = True
        status.update(f"• {escape(self._status_label)} ({elapsed}s • esc to interrupt)")

    def _refresh_footer(self) -> None:
        left = f"{self.session_context.model} · {self.session_context.cwd}"
        remaining = self.manager.context_remaining_percent()
        right_parts = []
        if self.background_tasks.running_count:
            right_parts.append(f"{self.background_tasks.running_count} background")
        if self.agent_manager.running_count:
            count = self.agent_manager.running_count
            right_parts.append(f"{count} {'Agent' if count == 1 else 'Agents'}")
        if remaining is not None:
            right_parts.append(f"{remaining}% context left")
        right = " · ".join(right_parts)
        self.query_one("#footer-left", Static).update(escape(left))
        self.query_one("#footer-right", Static).update(escape(right))

    def action_interrupt(self) -> None:
        if not self.active_turn or self.cancellation_token is None:
            return
        self.turn_controller.interrupt()
        self._set_status("Interrupt requested")

    def action_cancel_or_quit(self) -> None:
        if self.active_turn:
            self.action_interrupt()
        else:
            self.exit()

    def on_unmount(self) -> None:
        if self._owns_agent_manager:
            self.agent_manager.close()
        if self._owns_background_tasks:
            self.background_tasks.close()

    def _show_background_tasks(self) -> None:
        self._append_cell(
            Static(
                Text(self.background_tasks.status_text()),
                classes="context-cell",
                markup=False,
            )
        )

    def _show_agents(self) -> None:
        self._append_cell(
            Static(
                Text(self.agent_manager.status_text()),
                classes="context-cell",
                markup=False,
            )
        )

    def _start_agent_stop(self, agent_id: str) -> None:
        if not agent_id:
            self._append_cell(Static("■ Usage: /agent stop <id>", classes="error-cell"))
            return
        if self.active_turn:
            return
        self._begin_activity(f"Stopping {agent_id}")
        self.run_worker(
            lambda: self._run_agent_stop(agent_id),
            name="agent-stop",
            group="agent",
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def _run_agent_stop(self, agent_id: str) -> None:
        try:
            self.agent_manager.stop(agent_id)
        except BaseException as error:
            self.call_from_thread(self._show_task_stop_error, str(error))
        finally:
            self.call_from_thread(self._finish_activity)

    def _drain_agent_events(self) -> None:
        events = self.agent_manager.drain_events()
        if not events:
            return
        try:
            for event in events:
                self._show_agent_event(event)
            self._refresh_footer()
        except NoMatches:
            return

    def _show_agent_event(self, event: AgentEvent) -> None:
        style = "error-cell" if event.status == "failed" else "notice-cell"
        status = "started" if event.status == "starting" else event.status
        self._append_cell(
            Static(
                f"• Child Agent {escape(status)}\n"
                f"  {escape(event.agent_id)} · {escape(_bounded(event.description))}",
                classes=style,
            )
        )

    def _start_task_stop(self, task_id: str) -> None:
        if not task_id:
            self._append_cell(Static("■ Usage: /task stop <id>", classes="error-cell"))
            return
        if self.active_turn:
            return
        self._begin_activity(f"Stopping {task_id}")
        self.run_worker(
            lambda: self._run_task_stop(task_id),
            name="task-stop",
            group="agent",
            thread=True,
            exclusive=True,
            exit_on_error=False,
        )

    def _run_task_stop(self, task_id: str) -> None:
        try:
            self.background_tasks.stop(task_id)
        except BaseException as error:
            self.call_from_thread(self._show_task_stop_error, str(error))
        finally:
            self.call_from_thread(self._finish_activity)

    def _show_task_stop_error(self, message: str) -> None:
        self._append_cell(Static(f"■ {escape(message)}", classes="error-cell"))

    def _drain_task_events(self) -> None:
        events = self.background_tasks.drain_events()
        if not events:
            return
        try:
            for event in events:
                self._show_task_event(event)
            self._refresh_footer()
        except NoMatches:
            # The interval can race with Textual removing widgets on shutdown.
            return

    def _show_task_event(self, event: TaskEvent) -> None:
        labels = {
            "running": "started",
            "completed": "completed",
            "failed": "failed",
            "stopped": "stopped",
        }
        suffix = f" (exit {event.exit_code})" if event.exit_code is not None else ""
        style = "error-cell" if event.status == "failed" else "notice-cell"
        self._append_cell(
            Static(
                f"• Background task {labels[event.status]}{suffix}\n"
                f"  {escape(event.task_id)} · {escape(_bounded(event.command))}",
                classes=style,
            )
        )


def _tool_status(name: str, arguments: dict[str, Any]) -> str:
    if name == "execute":
        return f"Running {_bounded(arguments.get('command', '?'))}"
    if name == "todo":
        return "Updating plan"
    if name == "spawn_agent":
        return f"Starting Agent {_bounded(arguments.get('description', '?'))}"
    if name == "agent":
        return f"Managing Agent {arguments.get('action', '?')}"
    return _tool_description(name, arguments).removeprefix("• ")


def _tool_description(name: str, arguments: dict[str, Any]) -> str:
    if name == "skill":
        return f"• Loaded Skill\n  └ {_bounded(arguments.get('name', '?'))}"
    if name.startswith("mcp__"):
        return f"• Called MCP tool\n  └ {_bounded(name)}"
    if name == "execute":
        return f"• Ran {_bounded(arguments.get('command', '?'))}"
    if name == "search":
        query = _bounded(arguments.get("query", "?"))
        path = _bounded(arguments.get("path") or ".")
        return f"• Explored\n  └ Search {query} in {path}"
    if name == "read":
        return f"• Explored\n  └ Read {_bounded(arguments.get('path', '?'))}"
    if name in {"write", "patch", "delete"}:
        return f"• Edited {_bounded(arguments.get('path', '?'))}"
    if name == "spawn_agent":
        return f"• Started Agent\n  └ {_bounded(arguments.get('description', '?'))}"
    if name == "agent":
        agent_id = arguments.get("agent_id") or "all"
        return (
            f"• Managed Agent\n  └ {arguments.get('action', '?')} {_bounded(agent_id)}"
        )
    return f"• {name}"


def _bounded(value: Any, limit: int = 120) -> str:
    rendered = " ".join(str(value).splitlines())
    return rendered if len(rendered) <= limit else f"{rendered[: limit - 3]}..."


def run_tui(
    session_context: SessionContext | None = None,
    manager: ContextManager | None = None,
    *,
    session_handle: SessionHandle | None = None,
    memory_manager: MemoryManager | None = None,
    capability_runtime: CapabilityRuntime | None = None,
    background_tasks: BackgroundTaskManager | None = None,
    todo_state: TodoState | None = None,
    agent_manager: AgentManager | None = None,
) -> None:
    """Capture one session and run the full-screen application."""
    context = session_context or SessionContext.capture()
    context_manager = manager or ContextManager.capture(context)
    CodingKidApp(
        context,
        context_manager,
        session_handle=session_handle,
        memory_manager=memory_manager,
        capability_runtime=capability_runtime,
        background_tasks=background_tasks,
        todo_state=todo_state,
        agent_manager=agent_manager,
    ).run()
