def seed(products):
    products.create(None, "Vegetables", "Tomatoes", 1200, "kg", 10)
    products.create(None, "Tubers", "Cassava", 700, "kg", 10)
    products.create(None, "Oils", "Palm oil", 2800, "litre", 10)


def test_search_name_and_category(products):
    seed(products)
    assert [p["name"] for p in products.search("tom")] == ["Tomatoes"]
    assert [p["name"] for p in products.search("OILS")] == ["Palm oil"]


def test_synonym_search(products):
    seed(products)
    assert [p["name"] for p in products.search("garri")] == ["Cassava"]


def test_empty_query_returns_all_sorted_by_price(products):
    seed(products)
    assert [p["price"] for p in products.search("")] == [700, 1200, 2800]


def test_wildcards_and_injection_are_safe(products):
    seed(products)
    assert products.search("'; DROP TABLE products; --") == []
    assert len(products.search("")) == 3                  # table still exists


def test_negative_price_rejected(products):
    import pytest
    with pytest.raises(ValueError):
        products.create(None, "Vegetables", "Bad", -1, "kg", 1)
