from pkg.listops import chunked
from pkg.mathops import safe_div
from pkg.service import Service
from pkg.textops import initials
from pkg.timeops import minutes_to_hhmm


def test_safe_div_float():
    assert safe_div(7, 2) == 3.5


def test_initials_upper():
    assert initials("Ada Lovelace") == "A.L"


def test_chunked_exact():
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_hhmm_padded():
    assert minutes_to_hhmm(65) == "1:05"


def test_service():
    result = Service().summarize("Grace Hopper", [2.0, 4.0], 65)
    assert result["initials"] == "G.H"
    assert result["avg"] == 3.0
    assert result["batches"] == [[2.0, 4.0]]
    assert result["duration"] == "1:05"
