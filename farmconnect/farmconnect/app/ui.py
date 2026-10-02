"""Flet user interface (tested against Flet 1.0). Business rules live in repositories/services."""
import flet as ft

from app import theme as T
from app.config import ASSETS_DIR, DELIVERY_FEE
from app.db import Database
from app.repositories import (OrderRepository, ProductRepository, SellerRepository,
                              UserRepository)
from app.seclog import log
from app.security import LoginLocked, RateLimiter
from app.services.cart import Cart
from app.services.compare import CompareService, LocalProvider, SampleProvider
from app.services.images import match_image
from app.services.text import canonical_slug
from app.services.units import base_unit

# Kept for backwards compatibility with tests and older imports
GREEN, GREEN_DARK_MODE = T.LIGHT["primary"], T.DARK["primary"]
BADGE_BG, BADGE_TEXT, ERROR = T.SUN, T.SUN_TEXT, T.SNACK_ERROR
build_theme = T.build_theme

CATEGORIES = ["Vegetables", "Fruits", "Tubers", "Grains", "Oils", "Other"]
UNITS = ["kg", "piece", "litre", "g", "ml"]
TEXT_SCALES = {"Normal": 1.0, "Large": 1.25, "Extra large": 1.5}
C = ft.Colors
PAGE_SIZE = 24          # products drawn at once; "Show more" loads the next page


def default_compare_service(products: ProductRepository) -> CompareService:
    return CompareService([LocalProvider(products), SampleProvider("Jumia"),
                           SampleProvider("Konga"), SampleProvider("Temu")])


def naira(amount: float) -> str:
    return f"₦{amount:,.0f}"


async def open_url(url: str) -> None:
    await ft.UrlLauncher().launch_url(url)


class FarmApp:
    def __init__(self, page: ft.Page, db: Database, compare_service: CompareService | None = None,
                 rate_limiter: RateLimiter | None = None):
        self.page, self.db = page, db
        self.users, self.products = UserRepository(db), ProductRepository(db)
        self.orders, self.sellers = OrderRepository(db), SellerRepository(db)
        self.cart = Cart()
        self.compare_service = compare_service or default_compare_service(self.products)
        self.nav = None
        self.shown = PAGE_SIZE
        self.limiter = rate_limiter or RateLimiter(10, 60)     # 10 searches a minute per user
        self.user: dict | None = None
        self.tab = 0                      # 0 shop, 1 cart, 2 account
        self.scale = 1.0
        self.query = ""
        self.category: str | None = None  # active category chip
        self.results = None               # CompareResult after a search
        self.search_box = ft.TextField(
            label="Search produce (tomatoes, garri, palm oil)", on_submit=self.on_search,
            expand=True, border_radius=14, border_color=C.OUTLINE)

    # ---------- small building blocks ----------
    def fs(self, size: float) -> float:
        return round(size * self.scale)

    def text(self, value, size=16, bold=False, color=None) -> ft.Text:
        return ft.Text(value, size=self.fs(size), color=color,
                       weight=ft.FontWeight.W_700 if bold else ft.FontWeight.W_400)

    def muted(self, value, size=14) -> ft.Text:
        return self.text(value, size, color=C.ON_SURFACE_VARIANT)

    def toast(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(ft.SnackBar(
            content=ft.Text(("Problem: " if error else "") + message, size=self.fs(16),
                            color=T.SNACK_TEXT),
            bgcolor=T.SNACK_ERROR if error else T.SNACK_OK))

    def card(self, content, padding=16, highlight=False, width=None) -> ft.Container:
        return ft.Container(
            content, padding=padding, width=width, bgcolor=C.SURFACE_CONTAINER_LOW,
            border_radius=20,
            border=ft.Border.all(2 if highlight else 1,
                                 C.PRIMARY if highlight else C.OUTLINE_VARIANT))

    def pill(self, label: str, bg: str, fg: str) -> ft.Container:
        return ft.Container(self.text(label, 14, True, fg), bgcolor=bg, border_radius=14,
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4))

    def primary_button(self, label, on_click, tooltip, full_width=False) -> ft.Control:
        btn = ft.Button(
            content=label, on_click=on_click, tooltip=tooltip, height=48, expand=full_width,
            style=ft.ButtonStyle(
                bgcolor=C.PRIMARY, color=C.ON_PRIMARY,
                shape=ft.RoundedRectangleBorder(radius=14),
                text_style=ft.TextStyle(size=self.fs(16), weight=ft.FontWeight.W_600)))
        return ft.Row([btn]) if full_width else btn

    def field(self, label, **kw) -> ft.TextField:
        return ft.TextField(label=label, border_radius=14, border_color=C.OUTLINE, **kw)

    def dropdown(self, label, options, value=None, **kw) -> ft.Dropdown:
        return ft.Dropdown(label=label, value=value, border_radius=14, border_color=C.OUTLINE,
                           options=[ft.DropdownOption(o) if isinstance(o, str) else o
                                    for o in options], **kw)

    def hero(self, small: str, title: str, subtitle: str) -> ft.Container:
        return ft.Container(
            ft.Column([self.text(small, 14, True, T.HERO_SUBTEXT),
                       self.text(title, 30, True, T.HERO_TEXT),
                       self.text(subtitle, 16, color=T.HERO_SUBTEXT)], spacing=6),
            padding=ft.Padding.symmetric(horizontal=22, vertical=26), border_radius=24,
            gradient=ft.LinearGradient(begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                                       colors=[T.LEAF_DEEP, T.LEAF]))

    def price_of(self, product_id: int) -> float:
        return self.products.get(product_id)["price"]

    def tile(self, product: dict, width: int, height: int) -> ft.Control:
        """Product picture: real photo if one exists, otherwise an emoji on a crate-coloured tile."""
        path, alt = match_image(product["name"], product.get("category"))
        if (ASSETS_DIR / path).exists():
            return ft.Container(ft.Image(src=path, width=width, height=height, fit=ft.BoxFit.COVER,
                                         semantics_label=alt),
                                width=width, height=height, border_radius=14,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
        cat = product.get("category")
        emoji = T.PRODUCT_EMOJI.get(canonical_slug(product["name"]),
                                    T.CATEGORY_EMOJI.get(cat, "🌱"))
        return ft.Container(ft.Text(emoji, size=min(width, height) // 2, semantics_label=alt),
                            width=width, height=height, border_radius=14,
                            bgcolor=T.CATEGORY_TILE.get(cat, T.TILE_DEFAULT),
                            alignment=ft.Alignment.CENTER, tooltip=alt)

    # ---------- page shell ----------
    def shell(self, view: ft.Control) -> ft.Control:
        """Centres content with a comfortable maximum width on tablets and desktops."""
        body = ft.ResponsiveRow(
            [ft.Container(view, col={"xs": 12, "md": 10, "lg": 7},
                          padding=ft.Padding.only(bottom=24))],
            alignment=ft.MainAxisAlignment.CENTER)
        return ft.SafeArea(ft.Column([body], scroll=ft.ScrollMode.AUTO, expand=True), expand=True)

    def render(self) -> None:
        self.page.clean()
        self.page.navigation_bar = self.nav = None
        if self.user is None:
            self.page.add(self.shell(self.auth_view()))
        else:
            self.nav = self.page.navigation_bar = ft.NavigationBar(
                selected_index=self.tab, on_change=self.on_nav, bgcolor=C.SURFACE_CONTAINER_LOW,
                indicator_color=C.PRIMARY_CONTAINER,
                destinations=[ft.NavigationBarDestination(icon=ft.Icons.STOREFRONT, label="Shop"),
                              ft.NavigationBarDestination(
                                  icon=ft.Icons.SHOPPING_CART,
                                  label=f"Cart ({self.cart.count()})"),
                              ft.NavigationBarDestination(icon=ft.Icons.PERSON, label="Account")])
            view = [self.shop_view, self.cart_view, self.account_view][self.tab]()
            self.page.add(self.shell(view))
        self.page.update()

    def on_nav(self, e) -> None:
        self.tab = int(e.control.selected_index)
        self.render()

    # ---------- auth ----------
    def auth_view(self) -> ft.Control:
        name = self.field("Full name")
        email = self.field("Email", keyboard_type=ft.KeyboardType.EMAIL)
        password = self.field("Password (8+ characters)", password=True, can_reveal_password=True)
        role = self.dropdown("I want to", [ft.DropdownOption("buyer", "Buy produce"),
                                           ft.DropdownOption("farmer", "Sell my produce")],
                             value="buyer")

        def login(_):
            try:
                user = self.users.authenticate(email.value, password.value)
            except LoginLocked as err:
                return self.toast(str(err), True)
            if user is None:
                return self.toast("Email or password is wrong. Check both and try again.", True)
            self.user, self.tab = user, 0
            self.render()

        def register(_):
            try:
                self.users.create(name.value, email.value, password.value, role.value)
            except ValueError as err:
                return self.toast(str(err), True)
            login(_)

        form = ft.Column([
            self.text("Welcome", 22, True),
            self.muted("Log in, or fill in your name and choose Create account."),
            name, email, password, role,
            ft.Row([self.primary_button("Log in", login, "Log in to your account"),
                    ft.TextButton(content="Create account", on_click=register,
                                  tooltip="Create a new account with the details above")],
                   spacing=12)], spacing=14)
        return ft.Column([
            self.hero("🌿 FarmConnect", "Fresh from local farms",
                      "Buy straight from farmers and see how their prices compare."),
            self.card(form, padding=20)], spacing=16)

    # ---------- shop ----------
    async def on_search(self, _=None) -> None:
        if not self.limiter.allow(str(self.user["id"]) if self.user else "anonymous"):
            return self.toast("You are searching very fast. Wait a few seconds and try again.", True)
        self.query = self.search_box.value or ""
        self.results = None
        self.render_with_loading()
        try:
            self.results = await self.compare_service.compare(self.query)
        except Exception:                    # OWASP A10: never crash, never leak details
            log.exception("comparison search failed")
            self.toast("Search is not working right now. Try again in a moment.", True)
        self.render()

    def render_with_loading(self) -> None:
        self.page.clean()
        self.page.add(self.shell(ft.Column([
            self.search_card(), ft.Row([ft.ProgressRing(width=28, height=28),
                                        self.text("Checking local farmers and other stores…")],
                                       spacing=12)], spacing=16)))
        self.page.update()

    def search_card(self) -> ft.Control:
        return self.card(ft.Row(
            [self.search_box, self.primary_button("Search", self.on_search,
                                                  "Search local farmers and other stores")],
            spacing=10), padding=14)

    def clear_search(self, _=None) -> None:
        self.results, self.query, self.search_box.value = None, "", ""
        self.render()

    def pick_category(self, category: str | None) -> None:
        self.category, self.shown = category, PAGE_SIZE
        self.render()

    def category_chips(self) -> ft.Control:
        chips = []
        for name in [None] + CATEGORIES:
            selected = self.category == name
            label = name or "All"
            chips.append(ft.Chip(
                label=ft.Text(label, size=self.fs(15), color=C.ON_PRIMARY if selected else C.ON_SURFACE),
                selected=selected, show_checkmark=False, selected_color=C.PRIMARY,
                bgcolor=C.SURFACE_CONTAINER_HIGH, tooltip=f"Show {label.lower()}",
                on_select=lambda _, n=name: self.pick_category(n)))
        return ft.Row(chips, scroll=ft.ScrollMode.AUTO, spacing=8)

    def shop_view(self) -> ft.Control:
        first = self.user["name"].split()[0]
        parts: list[ft.Control] = [
            self.hero(f"Good day, {first}", "Fresh from local farms",
                      "Search once to compare farm prices with other stores."),
            self.search_card()]
        if self.results is None:
            parts.append(self.category_chips())
            items = self.products.list_active(self.category, limit=self.shown)
            total = self.products.count_active(self.category)
            parts.append(ft.Row([self.text(self.category or "Fresh near you", 20, True),
                                 self.muted(f"{total} items")],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
            if items:
                parts.append(ft.Row([self.local_card(p) for p in items], wrap=True,
                                    spacing=12, run_spacing=12))
                if total > len(items):
                    parts.append(ft.Row([ft.TextButton(
                        content=f"Show more ({total - len(items)} left)", on_click=self.show_more,
                        tooltip="Show more products")], alignment=ft.MainAxisAlignment.CENTER))
            else:
                parts.append(self.muted("Nothing in this category yet.", 16))
        else:
            parts += self.results_view()
        return ft.Column(parts, spacing=16)

    def saving_vs_next(self) -> int | None:
        """How much cheaper (per unit) the cheapest offer is than the next best, in percent."""
        ranked = [o for o in self.results.offers if o.comparable]
        if len(ranked) < 2:
            return None
        try:
            if base_unit(ranked[0].unit) != base_unit(ranked[1].unit) or ranked[1].per_unit <= 0:
                return None
        except KeyError:
            return None
        pct = round((1 - ranked[0].per_unit / ranked[1].per_unit) * 100)
        return pct if pct > 0 else None

    def results_view(self) -> list[ft.Control]:
        res = self.results
        out: list[ft.Control] = [ft.Row([
            ft.TextButton(content="← All produce", on_click=self.clear_search,
                          tooltip="Go back to all produce"),
            self.muted(f"{len(res.offers)} results for “{self.query}”")],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN)]
        if res.failed_stores:
            out.append(self.text("Could not reach " + ", ".join(res.failed_stores) +
                                 ". Showing the other results.", color=C.ERROR))
        if not res.offers:
            return out + [self.text(f"No results for “{self.query}”. Try another name, "
                                    "for example “tomatoes” or “beans”.")]
        out.append(self.muted("Prices are compared per kg, litre or piece."))
        saving = self.saving_vs_next()
        for o in res.offers:
            local = o.store == "Local farmers"
            store_pill = self.pill(o.store, C.PRIMARY if local else C.PRIMARY_CONTAINER,
                                   C.ON_PRIMARY if local else C.ON_PRIMARY_CONTAINER)
            badge = self.pill("Cheapest ✔", T.SUN, T.SUN_TEXT) if o.cheapest else ft.Container()
            per = (f"{naira(o.per_unit)} per {o.unit}" if o.comparable
                   else f"{naira(o.price)} per {o.unit}")
            lines = [ft.Row([store_pill, badge], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                     self.text(o.name, 18, True),
                     self.text(naira(o.price), 26, True, C.PRIMARY),
                     self.muted(f"for {o.qty:g} {o.unit}  ·  {per}")]
            if o.cheapest and saving:
                lines.append(self.text(f"{saving}% cheaper than the next best offer", 14, True))
            if local:
                pid = int(o.url.split(":")[1])
                lines.append(self.primary_button("Add to cart",
                                                 lambda _, pid=pid: self.add_to_cart(pid),
                                                 f"Add {o.name} to cart"))
            else:
                lines.append(ft.TextButton(content="Open store ↗", on_click=lambda _, u=o.url: open_url(u),
                                           tooltip=f"Open {o.store} in your browser"))
            out.append(self.card(ft.Column(lines, spacing=8), padding=16, highlight=o.cheapest))
        return out

    def local_card(self, p: dict) -> ft.Control:
        low = p["quantity"] < 10
        stock = (self.text(f"Only {p['quantity']} left", 14, True, C.ERROR) if low
                 else self.muted(f"{p['quantity']} available"))
        return self.card(ft.Column([
            self.tile(p, 140, 104),
            self.text(p["name"], 16, True),
            ft.Row([self.text(naira(p["price"]), 18, True, C.PRIMARY),
                    self.muted(f"per {p['unit']}")], spacing=4, wrap=True),
            stock,
            self.primary_button("Add", lambda _, pid=p["id"]: self.add_to_cart(pid),
                                f"Add {p['name']} to cart", full_width=True)], spacing=6),
            padding=10, width=162)

    def show_more(self, _=None) -> None:
        self.shown += PAGE_SIZE
        self.render()

    def add_to_cart(self, product_id: int) -> None:
        """Updates only the cart badge. Rebuilding the whole screen for one label is wasteful."""
        self.cart.add(product_id)
        if self.nav is not None:
            self.nav.destinations[1].label = f"Cart ({self.cart.count()})"
        self.toast("Added to cart.")
        self.page.update()

    # ---------- cart and checkout ----------
    def cart_view(self) -> ft.Control:
        prods = self.products.get_many(list(self.cart.items))      # one query, not one per line
        for pid in [i for i in self.cart.items
                    if i not in prods or prods[i]["status"] != "active"]:
            self.cart.remove(pid)                                  # removed or deactivated meanwhile
        if not self.cart.items:
            return ft.Column([self.card(ft.Column([
                ft.Text("🛒", size=self.fs(48)), self.text("Your cart is empty", 22, True),
                self.muted("Go to Shop and tap Add on anything you need.", 16)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=32)])
        rows: list[ft.Control] = [self.text("Your cart", 24, True)]
        for pid, qty in self.cart.items.items():
            p = prods[pid]
            rows.append(self.card(ft.Row([
                self.tile(p, 64, 64),
                ft.Column([self.text(p["name"], 17, True),
                           self.muted(f"{naira(p['price'])} × {qty}"),
                           self.text(naira(p["price"] * qty), 16, True, C.PRIMARY)],
                          spacing=2, expand=True),
                ft.IconButton(icon=ft.Icons.REMOVE, width=48, height=48,
                              tooltip=f"Remove one {p['name']}",
                              on_click=lambda _, pid=pid, q=qty: self.change_qty(pid, q - 1)),
                ft.IconButton(icon=ft.Icons.ADD, width=48, height=48,
                              tooltip=f"Add one more {p['name']}",
                              on_click=lambda _, pid=pid, q=qty: self.change_qty(pid, q + 1))],
                vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10), padding=12))
        address = self.field("Delivery address")
        pay = ft.RadioGroup(value="pay_on_delivery", content=ft.Column([
            ft.Radio(value="pay_on_delivery", label="Pay on delivery"),
            ft.Radio(value="card", label="Card or transfer (Paystack)")]))
        sub = self.cart.subtotal(lambda i: prods[i]["price"])
        def line(label, value, bold=False):
            return ft.Row([self.text(label, 16, bold), self.text(value, 16, bold)],
                          alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        rows.append(self.card(ft.Column([
            line("Items", naira(sub)), line("Delivery", naira(DELIVERY_FEE)), ft.Divider(),
            ft.Row([self.text("Total", 20, True), self.text(naira(sub + DELIVERY_FEE), 24, True, C.PRIMARY)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            address, self.text("Payment", 16, True), pay,
            self.primary_button("Place order", lambda _: self.place_order(address.value, pay.value),
                                "Place your order", full_width=True)], spacing=12), padding=18))
        return ft.Column(rows, spacing=12)

    def change_qty(self, pid: int, qty: int) -> None:
        self.cart.set_qty(pid, qty)
        self.render()

    def place_order(self, address: str, method: str) -> None:
        try:
            order_id = self.orders.create_order(self.user["id"], dict(self.cart.items),
                                                address, method, DELIVERY_FEE)
        except ValueError as err:
            return self.toast(str(err), True)
        self.cart.clear()
        self.results = None
        self.tab = 0
        self.toast(f"Order #{order_id} placed. The farmer will confirm it soon.")
        self.render()

    # ---------- account ----------
    def account_view(self) -> ft.Control:
        size = self.dropdown("Text size", list(TEXT_SCALES),
                             value=next(k for k, v in TEXT_SCALES.items() if v == self.scale),
                             on_select=self.on_text_size)
        dark = ft.Switch(label="Dark mode", value=self.page.theme_mode == ft.ThemeMode.DARK,
                         on_change=self.on_dark)
        role = "Farmer" if self.user["role"] == "farmer" else "Buyer"
        header = self.card(ft.Row([
            ft.CircleAvatar(content=ft.Text(self.user["name"][:1].upper(), size=self.fs(22),
                                            weight=ft.FontWeight.W_700, color=C.ON_PRIMARY),
                            bgcolor=C.PRIMARY, radius=30),
            ft.Column([self.text(self.user["name"], 20, True),
                       self.pill(role, C.PRIMARY_CONTAINER, C.ON_PRIMARY_CONTAINER)], spacing=4)],
            spacing=16), padding=18)
        parts = [header,
                 self.card(ft.Column([self.text("Display", 18, True), size, dark], spacing=12),
                           padding=18)]
        if self.user["role"] == "farmer":
            parts.append(self.card(ft.Column(self.farmer_form(), spacing=12), padding=18))
        parts.append(ft.TextButton(content="Log out", tooltip="Log out of your account",
                                   on_click=self.logout))
        return ft.Column(parts, spacing=14)

    def on_text_size(self, e) -> None:
        self.scale = TEXT_SCALES[e.control.value]
        self.render()

    def on_dark(self, e) -> None:
        self.page.theme_mode = ft.ThemeMode.DARK if e.control.value else ft.ThemeMode.LIGHT
        self.render()

    def farmer_form(self) -> list[ft.Control]:
        name = self.field("Product name")
        cat = self.dropdown("Category", CATEGORIES, value=CATEGORIES[0])
        price = self.field("Price in naira", keyboard_type=ft.KeyboardType.NUMBER)
        unit = self.dropdown("Sold per", UNITS, value="kg")
        qty = self.field("Quantity available", keyboard_type=ft.KeyboardType.NUMBER)
        place = self.field("Location")

        def publish(_):
            try:
                sid = self.sellers.get_or_create(self.user["id"], location=place.value or "")
                self.products.create(sid, cat.value, name.value.strip(), float(price.value),
                                     unit.value, int(qty.value), place.value or "")
            except (ValueError, AttributeError):
                return self.toast("Enter a name, a price and a quantity as numbers.", True)
            self.toast("Published. Buyers can now find it.")
            self.results = None
            self.render()

        return [self.text("Sell a product", 18, True), name, cat, price, unit, qty, place,
                self.primary_button("Publish product", publish, "Publish this product")]

    def logout(self, _) -> None:
        self.user, self.results, self.category, self.shown = None, None, None, PAGE_SIZE
        self.cart.clear()
        self.render()
