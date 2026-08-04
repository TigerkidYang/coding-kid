"""The plain terminal interface for Coding Kid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import inspect
import sys
from typing import Any

from coding_kid.agent import current_instructions, run_turn
from coding_kid.capabilities import CapabilityRuntime
from coding_kid.compaction import compact_context
from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextManager
from coding_kid.memory import MemoryManager
from coding_kid.provider import generate
from coding_kid.sessions import SessionError, SessionHandle, SessionInfo, SessionStore
from coding_kid.skills import SkillTurnState, explicit_skill_names
from coding_kid.tools import clear_todos, get_todos, set_todos, tool_definitions

InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], None]
MAX_TOOL_DISPLAY_CHARS = 140


@dataclass(frozen=True)
class SessionOptions:
    """Session lifecycle choice parsed by the version-selecting launcher."""

    mode: str = "new"
    session_id: str | None = None
    list_only: bool = False
    delete_session: str | None = None


def format_tool_call(name: str, arguments: dict[str, Any]) -> str:
    """Describe a tool action without exposing its input or output contents."""
    if name == "execute":
        rendered = f"[tool] execute: {arguments.get('command', '?')}"
    elif name == "search":
        query = arguments.get("query", "?")
        path = arguments.get("path") or "."
        rendered = f'[tool] search: "{query}" in {path}'
    elif name in {"read", "write", "patch", "delete"}:
        rendered = f"[tool] {name}: {arguments.get('path', '?')}"
    elif name == "todo":
        items = arguments.get("todos")
        if not isinstance(items, list):
            rendered = "[tool] todo"
        else:
            in_progress = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "in_progress"
            )
            completed = sum(
                1
                for item in items
                if isinstance(item, dict) and item.get("status") == "completed"
            )
            rendered = (
                f"[tool] todo: {len(items)} items "
                f"({in_progress} in progress, {completed} done)"
            )
    else:
        rendered = f"[tool] {name}"

    rendered = " ".join(str(rendered).splitlines())
    if len(rendered) > MAX_TOOL_DISPLAY_CHARS:
        return f"{rendered[: MAX_TOOL_DISPLAY_CHARS - 3]}..."
    return rendered


def chat(
    input_function: InputFunction = input,
    output_function: OutputFunction = print,
    *,
    session_handle: SessionHandle | None = None,
    memory_manager: MemoryManager | None = None,
    capability_runtime: CapabilityRuntime | None = None,
) -> None:
    """Keep accepting user messages until the user exits."""
    if session_handle is None:
        try:
            session_context = SessionContext.capture()
            manager = ContextManager.capture(session_context)
        except RuntimeError as error:
            output_function(f"Error: {error}")
            return
        clear_todos()
        ready = "Coding Kid is ready. Type /exit to quit."
    else:
        session_context = session_handle.context
        manager = session_handle.manager
        set_todos(session_handle.todos)
        ready = (
            f"Coding Kid is ready. Session {session_handle.info.session_id[:8]}. "
            "Type /exit to quit."
        )
    output_function(ready)
    if capability_runtime is not None:
        output_function(capability_runtime.summary())
        for warning in capability_runtime.warnings:
            output_function(f"[capability] warning: {warning}")
    if (
        memory_manager is not None
        and memory_manager.mode == "auto"
        and session_handle is not None
    ):
        output_function("[memory] checking eligible prior sessions")
        result = memory_manager.sync(
            generate,
            current_session_id=session_handle.info.session_id,
        )
        output_function(_format_memory_sync(result))

    def show_tool(name: str, arguments: dict[str, Any], result: str) -> None:
        output_function(format_tool_call(name, arguments))
        if result.startswith("ERROR:"):
            output_function(result)

    def show_context(message: str) -> None:
        output_function(message)

    while True:
        try:
            user_input = input_function("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_function("\nGoodbye.")
            return

        if user_input in {"/exit", "/quit"}:
            output_function("Goodbye.")
            return
        if not user_input:
            continue
        if user_input == "/context":
            definitions = tool_definitions()
            context_overlays: tuple[str, ...] = ()
            if capability_runtime is not None:
                definitions = capability_runtime.registry_for_turn(
                    SkillTurnState(capability_runtime.snapshot.skills)
                ).definitions()
                metadata = capability_runtime.skill_metadata()
                context_overlays = (metadata,) if metadata else ()
            output_function(
                manager.status_text(
                    current_instructions(session_context, context_overlays),
                    definitions,
                )
            )
            continue
        if user_input == "/capabilities":
            output_function(
                capability_runtime.status_text()
                if capability_runtime is not None
                else "Pluggable capabilities are not active."
            )
            continue
        if user_input == "/session":
            if session_handle is None:
                output_function("Session: ephemeral")
            else:
                output_function(_format_session(session_handle.info))
            continue
        if user_input == "/session save":
            if session_handle is None:
                output_function("Session persistence is not active.")
            else:
                try:
                    session_handle.retry_save()
                except Exception as error:
                    output_function(f"Fatal persistence error: {error}")
                else:
                    output_function("Session state is durable.")
            continue
        if user_input == "/sessions":
            if session_handle is None:
                output_function("Session persistence is not active.")
            else:
                output_function(_format_sessions(session_handle.store.list_sessions()))
            continue
        if user_input == "/memory":
            output_function(
                memory_manager.status_text()
                if memory_manager is not None
                else "Long-term memory is not active."
            )
            continue
        if user_input.startswith("/memory search "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                output_function(
                    _format_memories(
                        memory_manager.search(
                            user_input.removeprefix("/memory search ")
                        )
                    )
                )
            continue
        if user_input == "/memory sync":
            if memory_manager is None or session_handle is None:
                output_function("Long-term memory is not active.")
            else:
                output_function("[memory] synchronizing")
                output_function(
                    _format_memory_sync(
                        memory_manager.sync(
                            generate,
                            current_session_id=session_handle.info.session_id,
                            force=True,
                        )
                    )
                )
            continue
        if user_input.startswith("/remember "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                content = user_input.removeprefix("/remember ")
                global_scope = content.startswith("--global ")
                if global_scope:
                    content = content.removeprefix("--global ")
                try:
                    entry = memory_manager.add(content, global_scope=global_scope)
                except SessionError as error:
                    output_function(f"Error: {error}")
                else:
                    output_function(
                        f"Remembered {entry.memory_id[:8]} ({entry.scope})."
                    )
            continue
        if user_input.startswith("/forget "):
            if memory_manager is None:
                output_function("Long-term memory is not active.")
            else:
                try:
                    entry = memory_manager.forget(user_input.removeprefix("/forget "))
                except SessionError as error:
                    output_function(f"Error: {error}")
                else:
                    output_function(f"Forgot memory {entry.memory_id[:8]}.")
            continue
        if session_handle is not None and session_handle.dirty:
            output_function(
                "Persistence is pending. Use /session save before continuing."
            )
            continue
        if user_input == "/compact":
            snapshot = manager.clone()
            definitions = tool_definitions()
            compact_overlays: tuple[str, ...] = ()
            if capability_runtime is not None:
                definitions = capability_runtime.registry_for_turn(
                    SkillTurnState(capability_runtime.snapshot.skills)
                ).definitions()
                metadata = capability_runtime.skill_metadata()
                compact_overlays = (metadata,) if metadata else ()
            try:
                compact_context(
                    manager,
                    generate,
                    instructions=current_instructions(
                        session_context, compact_overlays
                    ),
                    tools=definitions,
                    trigger="manual",
                    on_context=show_context,
                )
            except KeyboardInterrupt:
                manager.restore(snapshot)
                output_function("\nCompaction interrupted.")
            except Exception as error:
                manager.restore(snapshot)
                output_function(f"Error: {error}")
            else:
                if session_handle is not None:
                    session_handle.todos = get_todos()
                    try:
                        session_handle.commit_state(kind="context_committed")
                    except Exception as error:
                        output_function(f"Fatal persistence error: {error}")
                        continue
            continue

        turn_start = manager.clone()
        todos_start = get_todos()
        request_context: list[Any] = []
        recalled_ids: tuple[str, ...] = ()
        if memory_manager is not None:
            request_context, recalled_ids = memory_manager.recall_context(user_input)
        skill_state: SkillTurnState | None = None
        registry = None
        overlays: tuple[str, ...] = ()
        if capability_runtime is not None:
            skill_state = SkillTurnState(capability_runtime.snapshot.skills)
            for skill_name in explicit_skill_names(
                user_input, capability_runtime.snapshot.skills
            ):
                request_context.append(
                    {
                        "role": "user",
                        "content": capability_runtime.load_skill(
                            skill_state, skill_name, explicit=True
                        ),
                    }
                )
            registry = capability_runtime.registry_for_turn(skill_state)
            metadata = capability_runtime.skill_metadata()
            overlays = (metadata,) if metadata else ()
        manager.conversation.append_user(user_input)
        try:
            turn_options: dict[str, Any] = {}
            if memory_manager is not None:
                turn_options = {
                    "request_context": request_context,
                    "on_memory_citations": lambda cited: memory_manager.record_usage(
                        set(cited) & set(recalled_ids)
                    ),
                }
            answer = run_turn(
                manager,
                on_tool=show_tool,
                on_context=show_context,
                session_context=session_context,
                **(
                    {
                        **turn_options,
                        "tool_registry": registry,
                        "instruction_overlays": overlays,
                    }
                    if capability_runtime is not None
                    else turn_options
                ),
            )
            if not answer.strip():
                raise RuntimeError("Model returned an empty answer")
        except KeyboardInterrupt:
            manager.restore(turn_start)
            set_todos(todos_start)
            if session_handle is not None:
                try:
                    session_handle.record_aborted(user_input, "interrupted")
                except Exception as error:
                    output_function(f"Persistence warning: {error}")
            output_function("\nTask interrupted. You can enter another request.")
            continue
        except Exception as error:
            manager.restore(turn_start)
            set_todos(todos_start)
            if session_handle is not None:
                try:
                    session_handle.record_aborted(user_input, str(error))
                except Exception as persistence_error:
                    output_function(f"Persistence warning: {persistence_error}")
            output_function(f"Error: {error}")
            continue

        if session_handle is not None:
            session_handle.todos = get_todos()
            try:
                session_handle.commit_state()
            except Exception as error:
                output_function(f"Coding Kid> {answer}")
                output_function(
                    "Fatal persistence error: the completed turn remains in memory "
                    f"but is not durable: {error}"
                )
                continue

        output_function(f"Coding Kid> {answer}")


def _format_session(info: SessionInfo) -> str:
    marker = " damaged" if info.damaged else ""
    return (
        f"{info.session_id[:8]}  {info.status}{marker}  {info.model}  "
        f"{info.updated_at}  {info.title}"
    )


def _format_sessions(items: list[SessionInfo]) -> str:
    if not items:
        return "No sessions for this project."
    return "\n".join(_format_session(item) for item in items)


def _format_memories(items: list[Any]) -> str:
    if not items:
        return "No matching memories."
    return "\n".join(
        f"{item.memory_id[:8]}  {item.scope}/{item.type}  {item.title}"
        for item in items
    )


def _format_memory_sync(result: Any) -> str:
    if result.error:
        return f"[memory] failed: {result.error}"
    return (
        f"[memory] extracted {result.extracted_sessions} session(s); "
        f"consolidated {result.consolidated_memories} memory item(s)"
    )


def _open_session(
    options: SessionOptions,
    current_context: SessionContext | None = None,
    store: SessionStore | None = None,
) -> SessionHandle:
    current = current_context or SessionContext.capture()
    session_store = store or SessionStore(current.project_root)
    if options.mode == "continue":
        handle = session_store.continue_latest()
    elif options.mode == "resume" and options.session_id:
        handle = session_store.resume(options.session_id)
    else:
        manager = ContextManager.capture(current)
        clear_todos()
        handle = session_store.create(current, manager, [])
    if handle.context.cwd != current.cwd:
        handle.close()
        raise SessionError(
            f"Resume from the session's original directory: {handle.context.cwd}"
        )
    if handle.context.model != current.model:
        handle.close()
        raise SessionError(
            "Resume with the session's original OPENROUTER_MODEL: "
            f"{handle.context.model}"
        )
    return handle


def main(options: SessionOptions | None = None) -> None:
    """Start the terminal chat."""
    selection = options or SessionOptions()
    try:
        current_context = SessionContext.capture()
        store = SessionStore(current_context.project_root)
        if selection.list_only:
            print(_format_sessions(store.list_sessions()))
            return
        if selection.delete_session:
            deleted = store.soft_delete(selection.delete_session)
            print(f"Deleted session {deleted.session_id[:8]} (evidence retained).")
            return
        handle = _open_session(selection, current_context, store)
    except RuntimeError as error:
        print(f"Error: {error}")
        return

    try:
        memory_manager = MemoryManager(handle.store)
        capability_runtime = CapabilityRuntime.capture(
            handle.context,
            context_window=handle.manager.budget.context_length,
        )
        if sys.stdin.isatty() and sys.stdout.isatty():
            from coding_kid.tui import run_tui

            tui_options: dict[str, Any] = {
                "session_handle": handle,
                "memory_manager": memory_manager,
            }
            if "capability_runtime" in inspect.signature(run_tui).parameters:
                tui_options["capability_runtime"] = capability_runtime
            run_tui(handle.context, handle.manager, **tui_options)
        else:
            chat_options: dict[str, Any] = {
                "session_handle": handle,
                "memory_manager": memory_manager,
            }
            if "capability_runtime" in inspect.signature(chat).parameters:
                chat_options["capability_runtime"] = capability_runtime
            chat(**chat_options)
    except RuntimeError as error:
        print(f"Error: {error}")
    finally:
        if "capability_runtime" in locals():
            capability_runtime.close()
        try:
            handle.close()
        except Exception as error:
            print(f"Persistence warning while closing session: {error}")
