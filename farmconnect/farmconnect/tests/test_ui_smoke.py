"""Smoke tests: every screen builds without errors (no display needed)."""
from types import SimpleNamespace

import flet as ft
import pytest

from app.seed import seed
from app.ui import FarmApp
from tests.helpers import FakePage, login, walk


@pytest.fixture
def app(db):
    seed(db)
    page = FakePage()
    return FarmApp(page, db), page


def test_seed_creates_20_products_and_is_repeatable(db, products):
    seed(db); seed(db)
    assert len(products.search("", limit=100)) == 20


def test_auth_screen_builds(app):
    a, page = app
    a.render()
    assert page.controls and page.navigation_bar is None


def test_all_tabs_build_for_farmer(app):
    a, page = app
    login(a)
    for tab in (0, 1, 2):
        a.tab = tab
        a.render()
        assert page.navigation_bar is not None


async def test_search_and_cart_flow(app):
    a, page = app
    login(a)
    a.search_box.value = "palm oil"
    await a.on_search()
    assert a.results.offers[0].cheapest and any(o.store == "Jumia" for o in a.results.offers)
    a.add_to_cart(a.products.search("palm")[0]["id"])
    a.tab = 1
    a.render()
    a.place_order("12 Market Road, Abuja", "pay_on_delivery")
    assert a.cart.count() == 0 and "placed" in page.dialogs[-1].content.value


def test_checkout_error_is_shown_not_raised(app):
    a, page = app
    login(a)
    a.cart.add(a.products.search("yam")[0]["id"], 999)
    a.place_order("addr", "card")
    assert page.dialogs[-1].content.value.startswith("Problem:")


def test_text_scale_changes_sizes(app):
    a, _ = app
    assert a.fs(16) == 16
    a.scale = 1.5
    assert a.fs(16) == 24


def test_locked_account_shows_message_not_crash(app):
    a, page = app
    for _ in range(5):
        a.users.authenticate("ngozi@farm.test", "wrong-password")
    a.render()
    # simulate the login button on the auth screen
    email = next(c for c in walk(page.controls) if isinstance(c, ft.TextField) and c.label == "Email")
    pw = next(c for c in walk(page.controls) if isinstance(c, ft.TextField) and c.label.startswith("Password"))
    login_btn = next(c for c in walk(page.controls) if isinstance(c, ft.Button) and c.content == "Log in")
    email.value, pw.value = "ngozi@farm.test", "farmpass123"
    login_btn.on_click(None)
    assert "Too many attempts" in page.dialogs[-1].content.value and a.user is None


async def test_unexpected_search_failure_is_handled(app):
    a, page = app
    login(a)

    async def boom(_): raise RuntimeError("internal detail")
    a.compare_service.compare = boom
    a.search_box.value = "yam"
    await a.on_search()
    assert "not working" in page.dialogs[-1].content.value
    assert "internal detail" not in page.dialogs[-1].content.value


# ---------- redesigned interface ----------
from app import theme as T


def texts(page):
    return [c.value for c in walk(page.controls) if isinstance(c, ft.Text)]


def test_every_seeded_product_has_its_own_emoji(db):
    from app.services.text import canonical_slug
    from app.seed import PRODUCTS
    for name, *_ in PRODUCTS:
        assert canonical_slug(name) in T.PRODUCT_EMOJI, f"no emoji for {name}"


def test_category_filter_shows_only_that_category(app):
    a, page = app
    login(a)
    a.pick_category("Fruits")
    shown = texts(page)
    assert "Pineapple" in shown and "Tomatoes" not in shown
    a.pick_category(None)
    assert "Tomatoes" in texts(page)


def test_logout_resets_category(app):
    a, _ = app
    login(a)
    a.pick_category("Grains")
    a.logout(None)
    assert a.category is None


async def test_cheapest_card_says_how_much_is_saved(app):
    a, page = app
    login(a)
    a.search_box.value = "palm oil"
    await a.on_search()
    assert any("cheaper than the next best offer" in t for t in texts(page))
    assert a.saving_vs_next() == 14          # 2,800 vs 3,250 per litre


async def test_back_button_returns_to_all_produce(app):
    a, page = app
    login(a)
    a.search_box.value = "palm oil"
    await a.on_search()
    assert a.results is not None
    a.clear_search()
    assert a.results is None and a.search_box.value == "" and "Fresh near you" in texts(page)


def test_low_stock_is_flagged_in_words(app):
    a, page = app
    login(a)
    a.products.create(None, "Fruits", "Mango", 900, "kg", 3)
    a.render()
    assert "Only 3 left" in texts(page)


def test_dark_and_light_themes_build():
    assert T.build_theme(dark=True).color_scheme.primary == T.DARK["primary"]
    assert T.build_theme(dark=False).color_scheme.primary == T.LIGHT["primary"]
