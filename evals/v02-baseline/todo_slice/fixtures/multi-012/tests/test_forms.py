import pytest
from forms import validate_record


def test_happy_path():
    assert validate_record({"name": " Ada ", "email": " Ada@Example.COM ", "age": "20"}) == {
        "name": "Ada",
        "email": "ada@example.com",
        "age_group": "adult",
    }


def test_invalid_email():
    with pytest.raises(ValueError):
        validate_record({"name": "Ada", "email": "ada.example.com", "age": "20"})


def test_senior():
    assert validate_record({"name": "Bob", "email": "bob@x.com", "age": "70"})["age_group"] == "senior"
