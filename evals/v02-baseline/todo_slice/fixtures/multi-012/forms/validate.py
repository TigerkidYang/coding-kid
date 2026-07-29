def require_fields(data: dict, fields: list[str]) -> None:
    missing = [f for f in fields if not data.get(f)]
    if missing:
        raise ValueError("missing: " + ",".join(missing))
