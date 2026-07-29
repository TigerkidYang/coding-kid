from forms.normalize import normalize_email
from forms.transform import age_group
from forms.validate import require_fields


def validate_record(data: dict) -> dict:
    require_fields(data, ["name", "email", "age"])
    email = normalize_email(data["email"])
    if "@" not in email:
        raise ValueError("invalid email")
    age = int(data["age"])
    return {
        "name": data["name"].strip(),
        "email": email,
        "age_group": age_group(age),
    }
