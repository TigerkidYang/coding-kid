from src.cart import Cart
from src.pricing import Pricing


def test_cart_total_respects_qty_and_discount():
    cart = Cart(Pricing())
    cart.add("A", 10.0, 3, discount_percent=10)
    assert cart.total() == 27.0
