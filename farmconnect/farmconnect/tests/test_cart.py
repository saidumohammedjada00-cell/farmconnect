import pytest
from app.services.cart import Cart

PRICES = {1: 1200.0, 2: 700.0}


def test_add_total_and_delivery():
    c = Cart()
    c.add(1, 2); c.add(2); c.add(1)
    assert c.items == {1: 3, 2: 1} and c.count() == 4
    assert c.subtotal(PRICES.get) == 4300
    assert c.total(PRICES.get, 1000) == 5300


def test_empty_cart_has_no_delivery_fee():
    assert Cart().total(PRICES.get, 1000) == 0


def test_set_qty_and_remove():
    c = Cart(); c.add(1, 2)
    c.set_qty(1, 5); assert c.items[1] == 5
    c.set_qty(1, 0); assert 1 not in c.items
    c.remove(99)                                       # removing a missing item is fine


def test_rejects_bad_quantity():
    with pytest.raises(ValueError):
        Cart().add(1, 0)
