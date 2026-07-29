def age_group(age: int) -> str:
    if age < 18:
        return "minor"
    if age < 65:
        return "adult"
    return "senior"
