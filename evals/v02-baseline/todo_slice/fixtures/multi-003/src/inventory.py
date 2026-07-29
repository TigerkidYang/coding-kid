class Inventory:
    """Track product stock levels."""

    def __init__(self):
        self._stock = {}

    def set_stock(self, sku: str, qty: int) -> None:
        self._stock[sku] = qty

    def available(self, sku: str, qty: int) -> bool:
        # BUG: off-by-one — should be >= qty, not > qty
        return self._stock.get(sku, 0) > qty

    def reserve(self, sku: str, qty: int) -> None:
        if not self.available(sku, qty):
            raise ValueError(f"insufficient stock for {sku}")
        self._stock[sku] -= qty
