"""Tests for the efficiency work: indexes, paging, caching, batching and start-up cost."""
import asyncio

import flet as ft
import pytest

from app.seed import seed
from app.services.compare import CompareService, LocalProvider, Offer, StoreProvider, TTLCache
from app.ui import PAGE_SIZE, FarmApp
from tests.helpers import FakePage, login, walk


def bulk_insert(db, n, category_id=1, start=0):
    with db.connect() as c:
        c.execute("INSERT OR IGNORE INTO categories (id, name) VALUES (1, 'Vegetables'), (2, 'Fruits')")
        c.executemany(
            "INSERT INTO products (category_id, name, slug, price, unit, quantity) "
            "VALUES (?, ?, ?, ?, 'kg', 10)",
            [(category_id, f"Item {i}", f"i{i}", 100 + i) for i in range(start, start + n)])


# ---------- database ----------
def test_wal_mode_enabled(db):
    with db.connect() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_browse_and_category_queries_use_indexes(db):
    bulk_insert(db, 500)
    with db.connect() as c:
        browse = c.execute("EXPLAIN QUERY PLAN SELECT * FROM products WHERE status='active' "
                           "ORDER BY price LIMIT 24").fetchall()
        category = c.execute("EXPLAIN QUERY PLAN SELECT * FROM products WHERE status='active' "
                             "AND category_id=1 ORDER BY price LIMIT 24").fetchall()
    plan = " ".join(r[3] for r in browse + category)
    assert "idx_products_status_price" in plan and "idx_products_status_cat_price" in plan
    assert "TEMP B-TREE" not in plan                  # no sorting of the whole table


def test_concurrent_writes_do_not_lock(db, products):
    import threading
    errors = []

    def work(k):
        try:
            for i in range(25):
                products.create(None, "Vegetables", f"T{k}-{i}", 100, "kg", 1)
        except Exception as e:                        # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=work, args=(k,)) for k in range(4)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert not errors and products.count_active() == 100


# ---------- repositories ----------
def test_category_filter_works_beyond_the_first_100_products(db, products):
    """Bug: the category chips used to filter only the 100 cheapest products."""
    bulk_insert(db, 150, category_id=1)                      # cheap vegetables
    bulk_insert(db, 5, category_id=2, start=1000)            # 5 expensive fruits
    fruits = products.list_active("Fruits", limit=24)
    assert len(fruits) == 5 and products.count_active("Fruits") == 5
    assert products.count_active() == 155 and products.count_active("Nonexistent") == 0
    assert products.list_active("Nonexistent") == []


def test_paging_is_ordered_and_complete(db, products):
    bulk_insert(db, 60)
    page1 = products.list_active(limit=24, offset=0)
    page2 = products.list_active(limit=24, offset=24)
    page3 = products.list_active(limit=24, offset=48)
    ids = [p["id"] for p in page1 + page2 + page3]
    assert len(ids) == 60 and len(set(ids)) == 60
    prices = [p["price"] for p in page1 + page2 + page3]
    assert prices == sorted(prices)


def test_get_many_is_one_query_and_ignores_missing(db, products):
    bulk_insert(db, 5)
    opened = []
    original = db.connect
    db.connect = lambda: (opened.append(1), original())[1]
    got = products.get_many([1, 2, 3, 3, 999])
    assert len(opened) == 1 and set(got) == {1, 2, 3}
    assert products.get_many([]) == {}


# ---------- cache and comparison service ----------
def test_cache_is_bounded_and_evicts_least_recently_used():
    cache = TTLCache(ttl=100, max_entries=3)
    for k in "abc":
        cache.set(k, k)
    cache.get("a")                      # "a" is now the most recently used
    cache.set("d", "d")                 # evicts "b"
    assert len(cache) == 3 and cache.get("b") is None and cache.get("a") == "a"


class Counting(StoreProvider):
    def __init__(self, name, fail=False, cacheable=True):
        self.name, self.fail, self.cacheable, self.calls = name, fail, cacheable, 0

    async def search(self, query):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        return [Offer(self.name, "Palm oil", 1000, 1, "l")]


async def test_local_results_are_never_cached_but_external_are(products):
    svc = CompareService([LocalProvider(products), Counting("Jumia")])
    first = await svc.compare("palm oil")
    assert [o.store for o in first.offers] == ["Jumia"]
    products.create(None, "Oils", "Palm oil", 900, "litre", 5)   # a farmer lists it afterwards
    second = await svc.compare("palm oil")
    assert {o.store for o in second.offers} == {"Local farmers", "Jumia"}   # fresh, not stale
    assert svc.providers[1].calls == 1                                      # external: cached


async def test_failed_store_is_retried_alone():
    good, bad = Counting("Good"), Counting("Bad", fail=True)
    svc = CompareService([good, bad])
    r1 = await svc.compare("x")
    assert r1.failed_stores == ["Bad"]
    bad.fail = False
    r2 = await svc.compare("x")
    assert r2.failed_stores == [] and len(r2.offers) == 2
    assert good.calls == 1 and bad.calls == 2        # the good store was NOT asked again


async def test_identical_simultaneous_searches_share_one_set_of_calls():
    class Slow(Counting):
        async def search(self, query):
            await asyncio.sleep(0.1)
            return await super().search(query)
    store = Slow("A")
    svc = CompareService([store])
    results = await asyncio.gather(*[svc.compare("palm oil") for _ in range(10)])
    assert store.calls == 1 and all(len(r.offers) == 1 for r in results)
    assert svc._inflight == {}                       # nothing left behind


async def test_one_cancelled_caller_does_not_break_the_others():
    class Slow(Counting):
        async def search(self, query):
            await asyncio.sleep(0.1)
            return await super().search(query)
    svc = CompareService([Slow("A")])
    t1 = asyncio.ensure_future(svc.compare("x"))
    t2 = asyncio.ensure_future(svc.compare("x"))
    await asyncio.sleep(0.01)
    t1.cancel()
    assert len((await t2).offers) == 1


# ---------- UI ----------
@pytest.fixture
def app(db):
    seed(db)
    page = FakePage()
    a = FarmApp(page, db)
    login(a)
    return a, page


def test_add_to_cart_updates_badge_without_rebuilding_screen(app):
    a, page = app
    a.render()
    before = list(page.controls)
    cleans = []
    page.clean = lambda: cleans.append(1)
    a.add_to_cart(a.products.list_active()[0]["id"])
    assert cleans == [] and page.controls == before          # no rebuild
    assert a.nav.destinations[1].label == "Cart (1)"


def test_only_one_page_of_products_is_built_and_show_more_loads_the_rest(app):
    a, page = app
    bulk_insert(a.db, 40, category_id=2, start=5000)         # 60 products in total
    a.render()
    cards = lambda: sum(1 for c in walk(page.controls) if isinstance(c, ft.Button) and c.content == "Add")
    assert cards() == PAGE_SIZE
    assert any(isinstance(c, ft.TextButton) and c.content.startswith("Show more") for c in walk(page.controls))
    a.show_more()
    assert cards() == 2 * PAGE_SIZE
    a.show_more()
    assert cards() == 60
    assert not any(isinstance(c, ft.TextButton) and str(c.content).startswith("Show more")
                   for c in walk(page.controls))


def test_changing_category_resets_paging(app):
    a, _ = app
    a.show_more(); a.show_more()
    a.pick_category("Fruits")
    assert a.shown == PAGE_SIZE


def test_cart_loads_all_lines_in_one_query_and_drops_deleted_products(app):
    a, page = app
    ids = [p["id"] for p in a.products.list_active(limit=5)]
    for i in ids:
        a.cart.add(i)
    opened = []
    original = a.db.connect
    a.db.connect = lambda: (opened.append(1), original())[1]
    a.tab = 1
    a.render()
    assert len(opened) == 1                                  # not one per cart line
    a.db.connect = original
    with a.db.connect() as c:
        c.execute("UPDATE products SET status='inactive' WHERE id=?", (ids[0],))
    a.render()                                               # must not crash on a vanished product
    assert ids[0] not in a.cart.items and len(a.cart.items) == 4


async def test_two_sessions_share_one_cache(db):
    seed(db)
    from app.ui import default_compare_service
    shared = default_compare_service(a_products := FarmApp(FakePage(), db).products)
    s1, s2 = FarmApp(FakePage(), db, shared), FarmApp(FakePage(), db, shared)
    assert s1.compare_service is s2.compare_service
    await s1.compare_service.compare("palm oil")
    jumia = next(p for p in shared.providers if p.name == "Jumia")
    calls = []
    original = jumia.search
    async def spy(q): calls.append(q); return await original(q)
    jumia.search = spy
    await s2.compare_service.compare("palm oil")             # a different user, same search
    assert calls == []                                       # served from the shared cache


def test_start_up_work_runs_once_not_per_session(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "once.db"))
    import app.seed as seed_module
    runs = []
    monkeypatch.setattr(main, "seed", lambda db: runs.append(1))
    app_main = main.make_main()
    for _ in range(3):                                       # three visitors
        app_main(FakePage())
    assert runs == [1]


# ---------- full-text search ----------
def seed_small(products):
    products.create(None, "Vegetables", "Tomatoes", 1200, "kg", 10)
    products.create(None, "Tubers", "Cassava", 700, "kg", 10)
    products.create(None, "Oils", "Palm oil", 2800, "litre", 10)
    products.create(None, "Fruits", "Pineapple", 1500, "piece", 10)


def names(rows):
    return [r["name"] for r in rows]


def test_fts_is_active_and_matches_like_behaviour(db, products):
    seed_small(products)
    assert db.fts
    assert names(products.search("mato")) == ["Tomatoes"]            # substring, as before
    assert names(products.search("PALM OIL")) == ["Palm oil"]        # case-insensitive phrase
    assert names(products.search("oils")) == ["Palm oil"]            # category column
    assert names(products.search("garri")) == ["Cassava"]            # local-name synonym
    assert names(products.search("to")) == ["Tomatoes"]              # too short for trigrams: LIKE fallback
    assert products.search("zzzzz") == []
    assert len(products.search("")) == 4


def test_fts_query_is_not_injectable(db, products):
    seed_small(products)
    for evil in ['" OR 1=1 --', "'; DROP TABLE products; --", 'name:* NEAR(a b)', '"']:
        products.search(evil)                                        # must not raise
    assert products.count_active() == 4


def test_fts_index_follows_inserts_updates_and_deletes(db, products):
    seed_small(products)
    with db.connect() as c:
        c.execute("UPDATE products SET name='Sweet mango' WHERE name='Pineapple'")
    assert names(products.search("mango")) == ["Sweet mango"] and products.search("pineapple") == []
    with db.connect() as c:
        c.execute("DELETE FROM products WHERE name='Sweet mango'")
    assert products.search("mango") == []


def test_inactive_products_are_hidden_from_search(db, products):
    seed_small(products)
    with db.connect() as c:
        c.execute("UPDATE products SET status='inactive' WHERE name='Cassava'")
    assert products.search("cassava") == []


def test_index_is_built_for_a_database_created_before_fts(tmp_path):
    from app.db import Database
    from app.repositories import ProductRepository
    old = Database(str(tmp_path / "old.db")); old.init()
    repo = ProductRepository(old)
    seed_small(repo)
    with old.connect() as c:                       # simulate an old database without the index
        c.executescript("DROP TRIGGER products_fts_ai; DROP TRIGGER products_fts_ad; "
                        "DROP TRIGGER products_fts_au; DROP TABLE products_fts;")
    upgraded = Database(str(tmp_path / "old.db")); upgraded.init()
    assert upgraded.fts and names(ProductRepository(upgraded).search("mato")) == ["Tomatoes"]


def test_search_falls_back_to_like_when_fts_is_unavailable(db, products):
    seed_small(products)
    db.fts = False
    assert names(products.search("mato")) == ["Tomatoes"]
    assert names(products.search("garri")) == ["Cassava"]


def test_search_plan_uses_the_full_text_index(db, products):
    seed_small(products)
    with db.connect() as c:
        plan = " ".join(r[3] for r in c.execute(
            "EXPLAIN QUERY PLAN SELECT p.id FROM products p WHERE p.status='active' AND p.id IN "
            "(SELECT rowid FROM products_fts WHERE products_fts MATCH '\"mato\"') "
            "ORDER BY p.price LIMIT 20").fetchall())
    assert "products_fts" in plan


# ---------- thumbnails and rate limiting ----------
def _photo(size=(2400, 1800)):
    """A synthetic 'photo': smooth gradient plus noise, so JPEG sizes are realistic."""
    import io, random
    from PIL import Image
    w, h = size
    img = Image.effect_noise((w, h), 25).convert("RGB")
    grad = Image.linear_gradient("L").resize((w, h)).convert("RGB")
    img = Image.blend(img, grad, 0.7)
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def test_upload_also_creates_a_much_smaller_thumbnail(tmp_path):
    from PIL import Image
    from app.uploads import save_product_image
    from tests.fake_clamd import FakeClamd
    from app.uploads import ClamAVScanner
    server = FakeClamd()
    try:
        name = save_product_image(_photo(), tmp_path, ClamAVScanner(port=server.port, timeout=2))
    finally:
        server.close()
    full, thumb = tmp_path / name, tmp_path / "thumbs" / name
    assert thumb.exists()
    with Image.open(thumb) as t, Image.open(full) as f:
        assert max(t.size) == 320 and max(f.size) == 1200
    assert thumb.stat().st_size * 5 < full.stat().st_size      # at least 5x smaller to download


def test_rate_limiter_blocks_then_recovers_and_isolates_users():
    from app.security import RateLimiter
    now = [0.0]
    rl = RateLimiter(3, 60, clock=lambda: now[0])
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b")                                       # other users unaffected
    now[0] = 61
    assert rl.allow("a")                                       # window passed


def test_rate_limiter_memory_stays_bounded():
    from app.security import RateLimiter
    now = [0.0]
    rl = RateLimiter(1, 10, clock=lambda: now[0])
    for i in range(10_005):
        rl.allow(f"user{i}")
    now[0] = 100
    rl.allow("trigger-cleanup")
    assert len(rl._calls) < 100


async def test_eleventh_rapid_search_is_refused_without_calling_the_stores(app):
    a, page = app
    calls = []
    original = a.compare_service.compare
    async def spy(q): calls.append(q); return await original(q)
    a.compare_service.compare = spy
    a.search_box.value = "yam"
    for _ in range(11):
        await a.on_search()
    assert len(calls) == 10
    assert "searching very fast" in page.dialogs[-1].content.value
