from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from coding_kid.context import SessionContext
from coding_kid.context_manager import ContextBudget, ContextManager
from coding_kid.memory import MemoryManager
from coding_kid.sessions import SessionStore


def response_json(value: Any) -> SimpleNamespace:
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=json.dumps(value))],
            )
        ]
    )


def make_store(tmp_path: Path) -> tuple[SessionStore, SessionContext, ContextManager]:
    context = SessionContext(
        cwd=tmp_path,
        operating_system="Test OS",
        shell="cmd.exe",
        model="test/model",
        local_date="2026-08-04",
        project_root=tmp_path,
        project_instructions=(),
    )
    manager = ContextManager(context, ContextBudget(32_768, "test"))
    return SessionStore(tmp_path, home=tmp_path / "home"), context, manager


def make_closed_session(
    store: SessionStore,
    context: SessionContext,
    manager: ContextManager,
    text: str,
) -> str:
    handle = store.create(context, manager, [])
    manager.conversation.append_user(text)
    manager.conversation.append_model_round(
        [{"role": "assistant", "content": "Acknowledged"}]
    )
    handle.commit_state()
    session_id = handle.info.session_id
    handle.close()
    return session_id


def test_explicit_project_and_global_memories_are_searchable(tmp_path: Path) -> None:
    store, _, _ = make_store(tmp_path)
    memories = MemoryManager(store)
    project = memories.add("Use pytest for this repository")
    user = memories.add("I prefer concise answers", global_scope=True)

    assert memories.search("pytest") == [project]
    assert memories.search("concise") == [user]
    assert project.scope == "project"
    assert user.scope == "user"


def test_forget_soft_deletes_memory(tmp_path: Path) -> None:
    store, _, _ = make_store(tmp_path)
    memories = MemoryManager(store)
    entry = memories.add("Keep this convention")

    forgotten = memories.forget(entry.memory_id[:8])

    assert forgotten.status == "forgotten"
    assert memories.search("convention") == []


def test_recall_is_bounded_request_only_context_with_provenance(
    tmp_path: Path,
) -> None:
    store, _, _ = make_store(tmp_path)
    memories = MemoryManager(store)
    entry = memories.add("Use the ALPHA naming convention")

    context, identifiers = memories.recall_context("Implement ALPHA")

    assert identifiers == (entry.memory_id,)
    assert context[0]["role"] == "user"
    assert entry.memory_id in context[0]["content"]
    assert "potentially stale" in context[0]["content"]


def test_two_stage_sync_extracts_and_consolidates_closed_session(
    tmp_path: Path,
) -> None:
    store, context, manager = make_store(tmp_path)
    session_id = make_closed_session(
        store,
        context,
        manager,
        "Always use ALPHA naming. api_key=super-secret-value",
    )
    memories = MemoryManager(store)
    calls: list[str] = []

    def provider(
        instructions: str, messages: list[Any], tools: list[Any], **kwargs: Any
    ) -> Any:
        calls.append(messages[0]["content"])
        if len(calls) == 1:
            assert "super-secret-value" not in messages[0]["content"]
            return response_json(
                {
                    "summary": "The user established a naming convention.",
                    "memories": [
                        {
                            "type": "feedback",
                            "title": "ALPHA naming",
                            "content": "Use ALPHA naming in this project.",
                            "keywords": ["ALPHA", "naming"],
                        }
                    ],
                }
            )
        candidate = json.loads(messages[0]["content"])["candidates"][0]
        return response_json(
            {
                "memories": [
                    {
                        "memory_id": "",
                        "type": "feedback",
                        "title": "ALPHA naming",
                        "content": "Use ALPHA naming in this project.",
                        "keywords": ["ALPHA", "naming"],
                        "source_ids": [candidate["source_id"]],
                    }
                ]
            }
        )

    result = memories.sync(provider, force=True)

    assert result.extracted_sessions == 1
    assert result.consolidated_memories == 1
    assert result.error is None
    recalled = memories.search("ALPHA")
    assert len(recalled) == 1
    assert recalled[0].sources == ({"session_id": session_id, "seq": 2},)
    assert recalled[0].origin == "automatic"


def test_successful_extraction_cursor_prevents_repeat_processing(
    tmp_path: Path,
) -> None:
    store, context, manager = make_store(tmp_path)
    make_closed_session(store, context, manager, "Remember ALPHA")
    memories = MemoryManager(store)
    responses = iter(
        [
            response_json({"summary": "none", "memories": []}),
        ]
    )

    first = memories.sync(lambda *args, **kwargs: next(responses), force=False)
    second = memories.sync(
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
        force=False,
    )

    assert first.extracted_sessions == 1
    assert second.extracted_sessions == 0


def test_concurrent_memory_sync_allows_only_one_pipeline_owner(
    tmp_path: Path,
) -> None:
    store, context, manager = make_store(tmp_path)
    make_closed_session(store, context, manager, "Remember ALPHA")
    first = MemoryManager(store)
    second = MemoryManager(store)
    entered = Event()
    release = Event()

    def slow_provider(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        assert release.wait(timeout=5)
        return response_json({"summary": "none", "memories": []})

    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(first.sync, slow_provider)
        assert entered.wait(timeout=5)
        blocked = second.sync(
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("concurrent provider call")
            )
        )
        release.set()
        completed = running.result(timeout=5)

    assert blocked.error == "memory maintenance is already running"
    assert completed.extracted_sessions == 1
    assert completed.error is None


def test_invalid_extraction_does_not_advance_cursor_and_is_retryable(
    tmp_path: Path,
) -> None:
    store, context, manager = make_store(tmp_path)
    make_closed_session(store, context, manager, "Remember ALPHA")
    memories = MemoryManager(store)

    failed = memories.sync(lambda *args, **kwargs: response_json({"wrong": True}))
    retried = memories.sync(
        lambda *args, **kwargs: response_json({"summary": "none", "memories": []})
    )

    assert failed.error is not None
    assert retried.extracted_sessions == 1


def test_usage_updates_only_selected_identifiers(tmp_path: Path) -> None:
    store, _, _ = make_store(tmp_path)
    memories = MemoryManager(store)
    used = memories.add("ALPHA")
    unused = memories.add("BETA")

    memories.record_usage([used.memory_id])

    assert memories.get(used.memory_id).use_count == 1
    assert memories.get(unused.memory_id).use_count == 0
