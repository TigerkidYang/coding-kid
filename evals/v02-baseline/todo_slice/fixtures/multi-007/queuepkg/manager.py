from queuepkg.storage import ListStorage
from queuepkg.validate import validate_task


class TaskQueue:
    def __init__(self):
        self._storage = ListStorage()

    def enqueue(self, task: dict) -> None:
        validate_task(task)
        self._storage.append(task)

    def dequeue(self) -> dict:
        if not self._storage.items:
            raise IndexError("empty queue")
        return self._storage.pop_front()

    def peek(self) -> dict:
        if not self._storage.items:
            raise IndexError("empty queue")
        return self._storage.peek_front()

    def size(self) -> int:
        return len(self._storage.items)
