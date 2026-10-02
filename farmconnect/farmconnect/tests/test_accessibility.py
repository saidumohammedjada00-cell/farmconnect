"""WCAG 2.2 checks that can be automated. Screen-reader and keyboard testing is still manual."""
import flet as ft
import pytest

from app.seed import seed
from app.ui import BADGE_BG, BADGE_TEXT, ERROR, GREEN, GREEN_DARK_MODE, FarmApp
from tests.helpers import FakePage, login, walk


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# WCAG 1.4.3 Contrast (Minimum): 4.5:1 for normal text
@pytest.mark.parametrize("fg,bg,label", [
    ("#FFFFFF", GREEN, "white on green button"),
    (GREEN, "#FAFAF5", "green on light background"),
    (GREEN_DARK_MODE, "#1E1E1E", "light green on dark background"),
    ("#FFFFFF", ERROR, "white on error snackbar"),
    (BADGE_TEXT, BADGE_BG, "cheapest badge"),
    ("#212121", "#FAFAF5", "body text, light"),
    ("#EEEEEE", "#1E1E1E", "body text, dark"),
    ("#EF9A9A", "#1E1E1E", "error text, dark"),
    ("#C62828", "#FAFAF5", "error text, light"),
])
def test_text_contrast_meets_aa(fg, bg, label):
    assert contrast(fg, bg) >= 4.5, f"{label}: {contrast(fg, bg):.2f}"


def test_known_bad_pairs_stay_out_of_use():
    """These failed when measured. If someone reuses them, this test documents why not."""
    assert contrast(GREEN, "#1E1E1E") < 4.5          # light-mode green on dark background
    assert contrast("#C62828", "#1E1E1E") < 4.5      # light-mode red text on dark background
    assert contrast("#FFFFFF", BADGE_BG) < 4.5       # white on orange


@pytest.fixture
def screens(db):
    seed(db)
    page = FakePage()
    app = FarmApp(page, db)
    login(app)
    return app, page


def all_screens(app, page):
    for tab in (0, 1, 2):
        if tab == 1:
            app.cart.add(app.products.search("yam")[0]["id"])
        app.tab = tab
        app.render()
        yield from walk(page.controls)
    app.user = None
    app.render()
    yield from walk(page.controls)


def test_every_interactive_control_has_a_name(screens):
    """WCAG 4.1.2 Name, Role, Value; 1.1.1 Non-text content; 3.3.2 Labels or instructions."""
    app, page = screens
    checked = 0
    for c in all_screens(app, page):
        if isinstance(c, (ft.Button, ft.TextButton, ft.IconButton)):
            assert c.tooltip, f"{type(c).__name__} has no accessible name"
            checked += 1
        if isinstance(c, (ft.TextField, ft.Dropdown)):
            assert c.label, "form field has no label"
            checked += 1
        if isinstance(c, ft.Image):
            assert c.semantics_label, "image has no alt text"
            checked += 1
    assert checked > 15          # guards against the walker silently finding nothing


def test_touch_targets_at_least_48(screens):
    """WCAG 2.5.8 Target Size (Minimum) needs 24px; Material guidance of 48px is used here."""
    app, page = screens
    for c in all_screens(app, page):
        if isinstance(c, ft.IconButton):
            assert c.width >= 48 and c.height >= 48


def test_text_is_never_below_14px_and_scales(screens):
    """WCAG 1.4.4 Resize Text: users can enlarge text to 150%."""
    app, page = screens
    for scale in (1.0, 1.5):
        app.scale = scale
        for c in all_screens(app, page):
            if isinstance(c, ft.Text) and c.size:
                assert c.size >= 14 * scale - 1


def test_errors_are_described_in_words_not_colour_alone(screens):
    """WCAG 1.4.1 Use of colour; 3.3.1 Error identification."""
    app, page = screens
    app.toast("Enter a delivery address.", error=True)
    assert page.dialogs[-1].content.value.startswith("Problem:")


async def test_cheapest_is_marked_with_text_not_colour_alone(screens):
    app, page = screens
    app.search_box.value = "palm oil"
    await app.on_search()
    texts = [c.value for c in walk(page.controls) if isinstance(c, ft.Text)]
    assert any("Cheapest" in t for t in texts)


# ---------- the redesigned theme (app/theme.py) ----------
from app import theme as T

_PAIRS = [("on_surface", "surface", 4.5), ("on_surface", "surface_container_low", 4.5),
          ("on_surface_variant", "surface_container_low", 4.5), ("on_surface_variant", "surface", 4.5),
          ("on_primary", "primary", 4.5), ("primary", "surface_container_low", 4.5),
          ("primary", "surface", 4.5), ("on_primary_container", "primary_container", 4.5),
          ("on_error", "error", 4.5), ("error", "surface", 4.5), ("error", "surface_container_low", 4.5),
          ("on_surface", "surface_container_high", 4.5),
          # WCAG 1.4.11: input borders and other UI boundaries need 3:1
          ("outline", "surface_container_low", 3.0), ("outline", "surface", 3.0)]


@pytest.mark.parametrize("mode,palette", [("light", T.LIGHT), ("dark", T.DARK)])
@pytest.mark.parametrize("fg,bg,minimum", _PAIRS)
def test_theme_palette_contrast(mode, palette, fg, bg, minimum):
    ratio = contrast(palette[fg], palette[bg])
    assert ratio >= minimum, f"{mode}: {fg} on {bg} is {ratio:.2f}, needs {minimum}"


@pytest.mark.parametrize("fg,bg", [(T.HERO_TEXT, T.LEAF), (T.HERO_TEXT, T.LEAF_DEEP),
                                   (T.HERO_SUBTEXT, T.LEAF), (T.HERO_SUBTEXT, T.LEAF_DEEP),
                                   (T.SUN_TEXT, T.SUN), (T.SNACK_TEXT, T.SNACK_OK),
                                   (T.SNACK_TEXT, T.SNACK_ERROR)])
def test_fixed_colour_pairs_meet_aa(fg, bg):
    """Hero text sits on a gradient, so both ends of the gradient are checked."""
    assert contrast(fg, bg) >= 4.5
