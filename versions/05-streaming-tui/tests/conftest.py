import pytest

from coding_kid.tools import clear_todos


@pytest.fixture(autouse=True)
def _reset_todos() -> None:
    clear_todos()
    yield
    clear_todos()
