import pytest


@pytest.fixture
def setup(users, products):
    buyer = users.create("Ada", "ada@mail.com", "password1")
    pid = products.create(None, "Vegetables", "Tomatoes", 1200, "kg", 10)
    return buyer, pid


def test_order_total_is_computed_from_database(orders, products, setup):
    buyer, pid = setup
    oid = orders.create_order(buyer, {pid: 3}, "12 Market Rd", "pay_on_delivery", 1000)
    order = orders.get(oid)
    assert order["total"] == 3 * 1200 + 1000
    assert order["items"][0]["unit_price"] == 1200
    assert products.get(pid)["quantity"] == 7          # stock reduced


def test_cannot_order_more_than_stock(orders, products, setup):
    buyer, pid = setup
    with pytest.raises(ValueError, match="Only 10"):
        orders.create_order(buyer, {pid: 11}, "addr", "card", 1000)
    assert products.get(pid)["quantity"] == 10


def test_failed_order_rolls_back_completely(orders, products, setup):
    buyer, pid = setup
    with pytest.raises(ValueError):
        orders.create_order(buyer, {pid: 2, 9999: 1}, "addr", "card", 1000)
    assert products.get(pid)["quantity"] == 10         # nothing half-saved


@pytest.mark.parametrize("items,addr,pay", [
    ({}, "addr", "card"), ({1: 1}, "  ", "card"), ({1: 1}, "addr", "bitcoin"), ({1: 0}, "addr", "card")])
def test_validation(orders, setup, items, addr, pay):
    buyer, _ = setup
    with pytest.raises(ValueError):
        orders.create_order(buyer, items, addr, pay, 1000)
