def kg_to_lb(kg: float) -> float:
    # BUG: divides instead of multiplies
    return round(kg / 2.20462, 5)
