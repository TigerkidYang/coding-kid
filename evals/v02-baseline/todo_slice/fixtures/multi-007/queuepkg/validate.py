def validate_task(task: dict) -> None:
    if "id" not in task or "title" not in task:
        raise ValueError("task requires id and title")
    # BUG: accepts empty title
    if task["title"] is None:
        raise ValueError("title must be non-empty")
