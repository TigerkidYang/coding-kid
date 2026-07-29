def to_snake(name: str) -> str:
    """Convert CamelCase or space-separated text to snake_case."""
    # BUG: only lowercases; does not insert underscores before capitals
    return name.replace(" ", "_").lower()
