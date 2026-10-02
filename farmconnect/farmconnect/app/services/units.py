"""Unit conversion so prices compare fairly (palm oil 5L vs 1L)."""

# factor to the base unit (kg for weight, l for volume, piece for count)
_TO_BASE = {"kg": ("kg", 1.0), "g": ("kg", 0.001),
            "l": ("l", 1.0), "litre": ("l", 1.0), "ml": ("l", 0.001),
            "piece": ("piece", 1.0)}


def base_unit(unit: str) -> str:
    return _TO_BASE[unit.lower()][0]


def price_per_unit(price: float, qty: float, unit: str) -> float:
    """Price per base unit (per kg, per litre, or per piece)."""
    if qty <= 0:
        raise ValueError("quantity must be greater than zero")
    if price < 0:
        raise ValueError("price cannot be negative")
    key = unit.lower()
    if key not in _TO_BASE:
        raise ValueError(f"unknown unit: {unit}")
    return price / (qty * _TO_BASE[key][1])
