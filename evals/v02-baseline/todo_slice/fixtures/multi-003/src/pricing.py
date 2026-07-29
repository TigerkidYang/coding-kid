class Pricing:
    """Apply percentage discounts to prices."""

    def apply_discount(self, price: float, percent: float) -> float:
        # BUG: adds discount instead of subtracting
        return round(price + price * (percent / 100.0), 2)
