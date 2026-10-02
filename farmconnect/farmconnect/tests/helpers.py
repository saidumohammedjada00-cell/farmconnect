"""Shared test helpers (kept out of test files so they do not import each other)."""
from types import SimpleNamespace

import flet as ft


class FakePage(SimpleNamespace):
    def __init__(self):
        super().__init__(controls=[], navigation_bar=None, theme_mode=ft.ThemeMode.LIGHT, dialogs=[])

    def clean(self): self.controls.clear()
    def add(self, *c): self.controls.extend(c)
    def update(self): pass
    def show_dialog(self, d): self.dialogs.append(d)


def login(app_, email="ngozi@farm.test", pw="farmpass123"):
    app_.user = app_.users.authenticate(email, pw)


def walk(controls):
    """Yield every control in a tree (follows .content and .controls)."""
    stack = list(controls)
    while stack:
        c = stack.pop()
        yield c
        inner = getattr(c, "content", None)
        if isinstance(inner, ft.Control):
            stack.append(inner)
        stack.extend(x for x in (getattr(c, "controls", None) or []) if isinstance(x, ft.Control))
