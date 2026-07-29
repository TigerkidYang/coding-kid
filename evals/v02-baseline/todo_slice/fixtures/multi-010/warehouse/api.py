from warehouse.orders import OrderService
from warehouse.pricing import PriceBook
from warehouse.stock import StockLedger


class Warehouse:
    def __init__(self):
        self.stock = StockLedger()
        self.prices = PriceBook()
        self.orders = OrderService(self.stock, self.prices)

    def seed(self, sku: str, qty: int, price: float) -> None:
        self.stock.set_qty(sku, qty)
        self.prices.set_price(sku, price)
