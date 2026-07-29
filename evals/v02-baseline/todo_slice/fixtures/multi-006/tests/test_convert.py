from convert.length import miles_to_km
from convert.temp import c_to_f
from convert.mass import kg_to_lb


def test_miles_to_km():
    assert miles_to_km(1) == 1.60934


def test_c_to_f():
    assert c_to_f(0) == 32.0
    assert c_to_f(100) == 212.0


def test_kg_to_lb():
    assert kg_to_lb(1) == 2.20462
