from src.inventory import Inventory


def test_available_exact_stock():
    inv = Inventory()
    inv.set_stock("A", 3)
    assert inv.available("A", 3) is True


def test_reserve_decrements():
    inv = Inventory()
    inv.set_stock("A", 5)
    inv.reserve("A", 2)
    assert inv.available("A", 3) is True
    assert inv.available("A", 4) is False
