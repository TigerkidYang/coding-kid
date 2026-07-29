def miles_to_km(miles: float) -> float:
    # BUG: uses 1.6 instead of 1.60934
    return round(miles * 1.6, 5)
