import pytest
from app.services.units import price_per_unit


def test_conversion():
    assert price_per_unit(5000, 5, "l") == 1000
    assert price_per_unit(500, 500, "g") == 1000      # 500 g costs 500 -> 1000 per kg
    assert price_per_unit(2000, 500, "ml") == 4000


def test_fair_comparison():
    assert price_per_unit(3400, 1, "l") < price_per_unit(15000, 3, "l")   # 3400 vs 5000 per litre


@pytest.mark.parametrize("args", [(100, 0, "kg"), (100, -1, "kg"), (-5, 1, "kg"), (100, 1, "bag")])
def test_bad_input(args):
    with pytest.raises(ValueError):
        price_per_unit(*args)
