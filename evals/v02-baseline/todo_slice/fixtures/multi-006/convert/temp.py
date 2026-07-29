def c_to_f(celsius: float) -> float:
    # BUG: missing * 9/5 — only adds 32
    return round(celsius + 32, 2)
