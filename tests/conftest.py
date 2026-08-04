from pathlib import Path

import pytest

from coding_kid.tools import clear_todos


@pytest.fixture(autouse=True)
def _reset_todos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODING_KID_HOME", str(tmp_path / "coding-kid-home"))
    clear_todos()
    yield
    clear_todos()
