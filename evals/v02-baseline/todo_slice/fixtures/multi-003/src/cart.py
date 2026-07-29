from src.pricing import Pricing


class Cart:
    """Shopping cart line items."""

    def __init__(self, pricing: Pricing | None = None):
        self.pricing = pricing or Pricing()
        self._items = []

    def add(
        self,
        sku: str,
        unit_price: float,
        qty: int,
        discount_percent: float = 0.0,
    ) -> None:
        self._items.append((sku, unit_price, qty, discount_percent))

    def total(self) -> float:
        total = 0.0
        for _, unit_price, qty, discount in self._items:
            discounted = self.pricing.apply_discount(unit_price, discount)
            # BUG: ignores qty
            total += discounted
        return round(total, 2)
