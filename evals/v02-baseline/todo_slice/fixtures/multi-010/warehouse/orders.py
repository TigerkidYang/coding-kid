class OrderService:
    def __init__(self, stock, prices):
        self.stock = stock
        self.prices = prices

    def place(self, sku: str, qty: int) -> dict:
        raise NotImplementedError
