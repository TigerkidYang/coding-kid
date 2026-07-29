from src.pricing import Pricing


def test_ten_percent_off():
    assert Pricing().apply_discount(100.0, 10) == 90.0


def test_zero_discount():
    assert Pricing().apply_discount(42.5, 0) == 42.5
