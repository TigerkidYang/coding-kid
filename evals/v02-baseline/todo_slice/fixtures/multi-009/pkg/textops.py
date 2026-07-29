def initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return ".".join(p[0].lower() for p in parts)
