def safe_div(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("b must be non-zero")
    return a // b
