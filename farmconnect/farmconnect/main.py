"""FarmConnect entry point. Run:  python main.py   (desktop)   or   flet run --web main.py"""
import os

import flet as ft

from app.config import ASSETS_DIR, DB_PATH
from app.db import Database
from app.repositories import ProductRepository
from app.security import RateLimiter
from app.seed import seed
from app.theme import build_theme
from app.ui import FarmApp, default_compare_service


def make_main():
    """Start-up work happens once here, not once per visitor."""
    db = Database(DB_PATH)
    db.init()
    if os.getenv("FARM_ENV") != "production":      # the sample farmer has a known password
        seed(db)                                    # sample catalogue; development only
    shared = default_compare_service(ProductRepository(db))   # one cache for all users
    limiter = RateLimiter(10, 60)                              # one limiter for all users

    def main(page: ft.Page) -> None:
        page.title = "FarmConnect"
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.theme = build_theme(dark=False)
        page.dark_theme = build_theme(dark=True)
        page.padding = 16
        page.bgcolor = None            # let the theme's surface colour show (light and dark)
        FarmApp(page, db, shared, limiter).render()

    return main


if __name__ == "__main__":
    ft.run(make_main(), assets_dir=str(ASSETS_DIR))
