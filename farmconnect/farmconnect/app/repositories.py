"""Data access layer. All SQL lives here and always uses parameters (no string-built SQL)."""
import sqlite3

from app.db import Database
from app.seclog import log, who
from app.security import (LoginLocked, LoginThrottle, hash_password, validate_email,
                          validate_password, verify_password)
from app.services.text import normalize_query, slugify, SYNONYMS


_DUMMY_HASH = hash_password("dummy-password-for-timing")   # equalises timing for unknown emails


class UserRepository:
    def __init__(self, db: Database, throttle: LoginThrottle | None = None):
        self.db = db
        self.throttle = throttle or LoginThrottle()

    def create(self, name: str, email: str, password: str, role: str = "buyer",
               phone: str | None = None) -> int:
        if not name or not name.strip():
            raise ValueError("Enter your name.")
        if not validate_email(email):
            raise ValueError("Enter a valid email address.")
        if not validate_password(password):
            raise ValueError("Password must be at least 8 characters.")
        if role not in ("buyer", "farmer"):   # admins are never self-registered
            raise ValueError("Choose buyer or farmer.")
        try:
            with self.db.connect() as c:
                cur = c.execute(
                    "INSERT INTO users (name, email, phone, password_hash, role) "
                    "VALUES (?,?,?,?,?)",
                    (name.strip(), email.strip().lower(), phone,
                     hash_password(password), role))
                return cur.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("That email is already registered.")

    def authenticate(self, email: str, password: str) -> dict | None:
        key = (email or "").strip().lower()
        try:
            self.throttle.check(key)
        except LoginLocked:
            log.warning("login blocked (locked) user=%s", who(key))
            raise
        with self.db.connect() as c:
            row = c.execute("SELECT * FROM users WHERE email = ?", (key,)).fetchone()
        ok = verify_password(password or "", row["password_hash"] if row else _DUMMY_HASH)
        if row and ok:
            self.throttle.success(key)
            user = dict(row)
            user.pop("password_hash")
            return user
        if self.throttle.failure(key):
            log.warning("account locked after repeated failures user=%s", who(key))
        else:
            log.info("login failed user=%s", who(key))
        return None


class ProductRepository:
    def __init__(self, db: Database):
        self.db = db

    def _category_id(self, c, name: str) -> int:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        return c.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()["id"]

    def create(self, seller_id: int | None, category: str, name: str, price: float,
               unit: str, quantity: int, location: str = "", description: str = "") -> int:
        if price < 0 or quantity < 0:
            raise ValueError("Price and quantity cannot be negative.")
        with self.db.connect() as c:
            cat_id = self._category_id(c, category)
            cur = c.execute(
                "INSERT INTO products (seller_id, category_id, name, slug, description, "
                "price, unit, quantity, location) VALUES (?,?,?,?,?,?,?,?,?)",
                (seller_id, cat_id, name, slugify(name), description, price, unit,
                 quantity, location))
            return cur.lastrowid

    def get(self, product_id: int) -> dict | None:
        with self.db.connect() as c:
            row = c.execute(
                "SELECT p.*, cat.name AS category FROM products p "
                "LEFT JOIN categories cat ON cat.id = p.category_id WHERE p.id = ?",
                (product_id,)).fetchone()
        return dict(row) if row else None

    def list_active(self, category: str | None = None, limit: int = 24,
                    offset: int = 0) -> list[dict]:
        """One page of active products, cheapest first. The category filter runs in SQL."""
        with self.db.connect() as c:
            sql = ("SELECT p.*, cat.name AS category FROM products p "
                   "LEFT JOIN categories cat ON cat.id = p.category_id WHERE p.status = 'active'")
            params: list = []
            if category:
                row = c.execute("SELECT id FROM categories WHERE name = ?", (category,)).fetchone()
                if row is None:
                    return []
                sql += " AND p.category_id = ?"
                params.append(row["id"])
            sql += " ORDER BY p.price, p.id LIMIT ? OFFSET ?"
            return [dict(r) for r in c.execute(sql, params + [limit, offset]).fetchall()]

    def count_active(self, category: str | None = None) -> int:
        with self.db.connect() as c:
            if category:
                row = c.execute(
                    "SELECT COUNT(*) AS n FROM products p JOIN categories cat "
                    "ON cat.id = p.category_id WHERE p.status = 'active' AND cat.name = ?",
                    (category,)).fetchone()
            else:
                row = c.execute("SELECT COUNT(*) AS n FROM products WHERE status = 'active'").fetchone()
            return row["n"]

    def get_many(self, ids: list[int]) -> dict[int, dict]:
        """Fetch several products in ONE query (avoids one query per cart line)."""
        ids = list(dict.fromkeys(ids))
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self.db.connect() as c:
            rows = c.execute(
                f"SELECT p.*, cat.name AS category FROM products p "
                f"LEFT JOIN categories cat ON cat.id = p.category_id WHERE p.id IN ({marks})",
                ids).fetchall()
        return {r["id"]: dict(r) for r in rows}

    def search(self, query: str = "", limit: int = 20) -> list[dict]:
        """Case-insensitive search on name or category, with local-name synonyms."""
        q = normalize_query(query)
        terms = {q}
        if q in SYNONYMS:                       # e.g. "garri" also matches "cassava"
            terms.add(SYNONYMS[q].replace("-", " "))
        if q and self.db.fts and all(len(t) >= 3 for t in terms):
            # Index lookup. IN (subquery) is deliberate: a JOIN here took 7 s on rare words.
            match = " OR ".join(f'"{t}"' for t in sorted(terms))     # terms are [a-z0-9 ] only
            sql = ("SELECT p.*, cat.name AS category FROM products p "
                   "LEFT JOIN categories cat ON cat.id = p.category_id "
                   "WHERE p.status = 'active' AND p.id IN "
                   "(SELECT rowid FROM products_fts WHERE products_fts MATCH ?) "
                   "ORDER BY p.price LIMIT ?")
            with self.db.connect() as c:
                return [dict(r) for r in c.execute(sql, (match, limit)).fetchall()]
        sql = ("SELECT p.*, cat.name AS category FROM products p "      # fallback: short words, old SQLite
               "LEFT JOIN categories cat ON cat.id = p.category_id "
               "WHERE p.status = 'active' AND (")
        clauses, params = [], []
        for t in terms:
            like = f"%{t}%"
            clauses.append("(LOWER(p.name) LIKE ? OR LOWER(cat.name) LIKE ?)")
            params += [like, like]
        sql += " OR ".join(clauses) + ") ORDER BY p.price LIMIT ?"
        params.append(limit)
        with self.db.connect() as c:
            return [dict(r) for r in c.execute(sql, params).fetchall()]


class OrderRepository:
    def __init__(self, db: Database):
        self.db = db

    def create_order(self, buyer_id: int, items: dict[int, int], address: str,
                     payment_method: str, delivery_fee: float) -> int:
        """Prices are read from the database, never trusted from the client."""
        if not items:
            raise ValueError("Your cart is empty.")
        if not address or not address.strip():
            raise ValueError("Enter a delivery address.")
        if payment_method not in ("pay_on_delivery", "card"):
            raise ValueError("Choose a payment method.")
        with self.db.connect() as c:
            total, lines = 0.0, []
            for pid, qty in items.items():
                if qty <= 0:
                    raise ValueError("Quantity must be at least 1.")
                row = c.execute("SELECT * FROM products WHERE id = ? AND status='active'",
                                (pid,)).fetchone()
                if row is None:
                    raise ValueError("A product in your cart is no longer available.")
                if row["quantity"] < qty:
                    raise ValueError(f"Only {row['quantity']} of {row['name']} left.")
                total += row["price"] * qty
                lines.append((pid, qty, row["price"]))
            cur = c.execute(
                "INSERT INTO orders (buyer_id, total, delivery_fee, address, payment_method) "
                "VALUES (?,?,?,?,?)",
                (buyer_id, total + delivery_fee, delivery_fee, address.strip(), payment_method))
            order_id = cur.lastrowid
            for pid, qty, price in lines:
                c.execute("INSERT INTO order_items (order_id, product_id, qty, unit_price) "
                          "VALUES (?,?,?,?)", (order_id, pid, qty, price))
                c.execute("UPDATE products SET quantity = quantity - ? WHERE id = ?", (qty, pid))
            return order_id

    def get(self, order_id: int) -> dict | None:
        with self.db.connect() as c:
            order = c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if not order:
                return None
            items = c.execute("SELECT * FROM order_items WHERE order_id = ?",
                              (order_id,)).fetchall()
        return {**dict(order), "items": [dict(i) for i in items]}


class SellerRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, user_id: int, farm_name: str = "", location: str = "") -> int:
        with self.db.connect() as c:
            row = c.execute("SELECT id FROM seller_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                return row["id"]
            return c.execute("INSERT INTO seller_profiles (user_id, farm_name, location) VALUES (?,?,?)",
                             (user_id, farm_name, location)).lastrowid
