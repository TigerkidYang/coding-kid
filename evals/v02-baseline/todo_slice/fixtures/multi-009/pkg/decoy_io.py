from pathlib import Path


def read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8").splitlines()
