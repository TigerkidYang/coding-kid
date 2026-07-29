import pytest
from warehouse import Warehouse


def test_adjust_and_line_total_and_order():
    wh = Warehouse()
    wh.seed("sku-1", 5, 3.5)
    wh.stock.adjust("sku-1", -2)
    assert wh.stock.get_qty("sku-1") == 3
    assert wh.prices.line_total("sku-1", 2) == 7.0
    result = wh.orders.place("sku-1", 2)
    assert result == {"sku": "sku-1", "qty": 2, "total": 7.0}
    assert wh.stock.get_qty("sku-1") == 1


def test_order_rejects_insufficient_stock():
    wh = Warehouse()
    wh.seed("sku-1", 1, 10.0)
    with pytest.raises(ValueError):
        wh.orders.place("sku-1", 2)
