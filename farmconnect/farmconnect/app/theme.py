"""Visual identity: palette, product tiles, and Flet themes.

Every text/background pair below is checked in tests/test_accessibility.py (WCAG 1.4.3 / 1.4.11).
"""
import dataclasses

import flet as ft

LEAF, LEAF_DEEP = "#1E6B3A", "#124A29"      # primary green and the hero gradient start
SUN, SUN_TEXT = "#F2B632", "#2B2100"        # "Cheapest" badge: dark text on sunflower
HERO_TEXT, HERO_SUBTEXT = "#FFFFFF", "#E3F1E6"
SNACK_OK, SNACK_ERROR, SNACK_TEXT = "#1E6B3A", "#B3261E", "#FFFFFF"

LIGHT = dict(
    primary=LEAF, on_primary="#FFFFFF",
    primary_container="#D7EBD3", on_primary_container="#0F3A1F",
    secondary_container="#E6EDE0", on_secondary_container="#17251C",
    error="#B3261E", on_error="#FFFFFF",
    surface="#F4F7EF", on_surface="#17251C", on_surface_variant="#4A5A50",
    outline="#66776B", outline_variant="#CFD8CB",
    surface_container_lowest="#FFFFFF", surface_container_low="#FFFFFF",
    surface_container="#EEF3E8", surface_container_high="#E6EDE0",
)
DARK = dict(
    primary="#7FD39B", on_primary="#06301A",
    primary_container="#1F4D31", on_primary_container="#CDEED7",
    secondary_container="#1E3226", on_secondary_container="#E6EFE8",
    error="#F2B8B5", on_error="#601410",
    surface="#0E1913", on_surface="#E6EFE8", on_surface_variant="#A9BAAE",
    outline="#7F9387", outline_variant="#2E4236",
    surface_container_lowest="#0A130E", surface_container_low="#16251C",
    surface_container="#1A2C21", surface_container_high="#1E3226",
)

# Soft crate colours behind each product emoji, by category
CATEGORY_TILE = {"Vegetables": "#DCEFCF", "Fruits": "#FFE2BF", "Tubers": "#F0DDC6",
                 "Grains": "#F5EAB8", "Oils": "#F7E3A0", "Other": "#F6D8C8"}
CATEGORY_EMOJI = {"Vegetables": "🥬", "Fruits": "🍎", "Tubers": "🍠", "Grains": "🌾",
                  "Oils": "🛢️", "Other": "🍯"}
PRODUCT_EMOJI = {
    "tomatoes": "🍅", "red-bell-pepper": "🫑", "scotch-bonnet": "🌶️", "onions": "🧅",
    "ugu-leaves": "🥬", "okra": "🌿", "spinach": "🥬", "yam": "🍠", "sweet-potato": "🍠",
    "cassava": "🥔", "plantain": "🍌", "banana": "🍌", "pineapple": "🍍", "watermelon": "🍉",
    "oranges": "🍊", "brown-beans": "🫘", "maize": "🌽", "rice-local": "🌾",
    "palm-oil": "🛢️", "honey": "🍯",
}
TILE_DEFAULT = "#E3EFD9"


def _scheme(values: dict) -> ft.ColorScheme:
    known = {f.name for f in dataclasses.fields(ft.ColorScheme)}
    return ft.ColorScheme(**{k: v for k, v in values.items() if k in known})


def build_theme(dark: bool = False) -> ft.Theme:
    return ft.Theme(color_scheme=_scheme(DARK if dark else LIGHT), use_material3=True,
                    font_family="Roboto")
