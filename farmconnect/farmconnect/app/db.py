"""Database connection and schema (SQLite for the MVP, PostgreSQL later)."""
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  phone TEXT,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('buyer','farmer','admin')),
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS seller_profiles (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  farm_name TEXT, location TEXT, verified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  seller_id INTEGER REFERENCES seller_profiles(id),
  category_id INTEGER REFERENCES categories(id),
  name TEXT NOT NULL, slug TEXT NOT NULL,
  description TEXT,
  price REAL NOT NULL CHECK(price >= 0),
  unit TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
  location TEXT,
  status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
-- browse and category pages: filter on status/category, sort by price, no table sort
CREATE INDEX IF NOT EXISTS idx_products_status_price ON products(status, price);
CREATE INDEX IF NOT EXISTS idx_products_status_cat_price ON products(status, category_id, price);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY,
  buyer_id INTEGER NOT NULL REFERENCES users(id),
  total REAL NOT NULL, delivery_fee REAL NOT NULL,
  address TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'placed',
  payment_method TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
  id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  qty INTEGER NOT NULL CHECK(qty > 0),
  unit_price REAL NOT NULL
);
"""

# Full-text search: trigram index = fast substring search ("mato" finds "Tomatoes").
# Kept in sync by triggers. If this SQLite build lacks FTS5/trigram, search falls back to LIKE.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(name, category, tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS products_fts_ai AFTER INSERT ON products BEGIN
  INSERT INTO products_fts(rowid, name, category)
  VALUES (new.id, new.name, COALESCE((SELECT name FROM categories WHERE id = new.category_id), ''));
END;
CREATE TRIGGER IF NOT EXISTS products_fts_ad AFTER DELETE ON products BEGIN
  DELETE FROM products_fts WHERE rowid = old.id;
END;
CREATE TRIGGER IF NOT EXISTS products_fts_au AFTER UPDATE OF name, category_id ON products BEGIN
  DELETE FROM products_fts WHERE rowid = old.id;
  INSERT INTO products_fts(rowid, name, category)
  VALUES (new.id, new.name, COALESCE((SELECT name FROM categories WHERE id = new.category_id), ''));
END;
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.fts = False          # set by init() when full-text search is available

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")   # safe with WAL, far fewer disk syncs
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as c:
            c.executescript(SCHEMA)
            c.execute("PRAGMA journal_mode = WAL")      # readers no longer block the writer
            try:
                c.executescript(FTS_SCHEMA)
                self.fts = True
                if (c.execute("SELECT COUNT(*) FROM products_fts").fetchone()[0] == 0
                        and c.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0):
                    c.execute("INSERT INTO products_fts(rowid, name, category) "      # existing data
                              "SELECT p.id, p.name, COALESCE(cat.name, '') FROM products p "
                              "LEFT JOIN categories cat ON cat.id = p.category_id")
            except sqlite3.OperationalError:
                self.fts = False
