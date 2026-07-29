def chunked(items: list, size: int) -> list[list]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[i:i + size + 1] for i in range(0, len(items), size)]
