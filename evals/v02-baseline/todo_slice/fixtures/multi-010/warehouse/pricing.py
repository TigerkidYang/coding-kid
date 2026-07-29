class PriceBook:
    def __init__(self):
        self._prices = {}

    def set_price(self, sku: str, price: float) -> None:
        self._prices[sku] = price

    def line_total(self, sku: str, qty: int) -> float:
        raise NotImplementedError
