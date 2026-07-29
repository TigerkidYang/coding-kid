class StockLedger:
    def __init__(self):
        self._qty = {}

    def set_qty(self, sku: str, qty: int) -> None:
        self._qty[sku] = qty

    def get_qty(self, sku: str) -> int:
        return self._qty.get(sku, 0)

    def adjust(self, sku: str, delta: int) -> None:
        raise NotImplementedError
