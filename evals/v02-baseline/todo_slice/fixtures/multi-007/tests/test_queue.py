import pytest
from queuepkg import TaskQueue


def test_fifo_order():
    q = TaskQueue()
    q.enqueue({"id": 1, "title": "a"})
    q.enqueue({"id": 2, "title": "b"})
    assert q.peek()["id"] == 1
    assert q.dequeue()["id"] == 1
    assert q.dequeue()["id"] == 2


def test_reject_empty_title():
    q = TaskQueue()
    with pytest.raises(ValueError):
        q.enqueue({"id": 1, "title": ""})


def test_empty_errors():
    q = TaskQueue()
    with pytest.raises(IndexError):
        q.peek()
