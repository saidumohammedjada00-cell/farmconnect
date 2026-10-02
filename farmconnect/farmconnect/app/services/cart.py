"""Shopping cart: dictionary of product_id -> quantity (O(1) update, O(n) total)."""
from typing import Callable


class Cart:
    def __init__(self):
        self.items: dict[int, int] = {}

    def add(self, product_id: int, qty: int = 1) -> None:
        if qty <= 0:
            raise ValueError("Quantity must be at least 1.")
        self.items[product_id] = self.items.get(product_id, 0) + qty

    def set_qty(self, product_id: int, qty: int) -> None:
        if qty <= 0:
            self.items.pop(product_id, None)
        else:
            self.items[product_id] = qty

    def remove(self, product_id: int) -> None:
        self.items.pop(product_id, None)

    def clear(self) -> None:
        self.items.clear()

    def count(self) -> int:
        return sum(self.items.values())

    def subtotal(self, price_of: Callable[[int], float]) -> float:
        return sum(price_of(pid) * qty for pid, qty in self.items.items())

    def total(self, price_of: Callable[[int], float], delivery_fee: float) -> float:
        return self.subtotal(price_of) + (delivery_fee if self.items else 0.0)
