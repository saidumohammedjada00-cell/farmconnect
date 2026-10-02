"""Measure the parts of FarmConnect that could be slow. Run: python scripts/benchmark.py [N]"""
import asyncio, os, sys, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import Database
from app.repositories import ProductRepository
from app.seed import seed
from app.ui import FarmApp
from tests.helpers import FakePage, login

N = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
NAMES = ["Tomatoes", "Yam", "Palm oil", "Okra", "Cassava", "Plantain", "Honey", "Beans", "Rice", "Maize"]


def timed(fn, runs=20):
    samples = []
    for _ in range(runs):
        t = time.perf_counter(); fn(); samples.append((time.perf_counter() - t) * 1000)
    samples.sort()
    return samples[len(samples) // 2]


def build(n):
    d = tempfile.mkdtemp()
    db = Database(os.path.join(d, "bench.db")); db.init(); seed(db)
    with db.connect() as c:
        c.executemany(
            "INSERT INTO products (seller_id, category_id, name, slug, price, unit, quantity, location) "
            "VALUES (1, 1, ?, ?, ?, 'kg', 50, 'Abuja')",
            [(f"{NAMES[i % 10]} grade {i}", f"p-{i}", 500 + i % 3000) for i in range(n)])
        c.execute("INSERT INTO products (seller_id, category_id, name, slug, price, unit, quantity) "
                  "VALUES (1, 1, 'Rare dragonfruit', 'rd', 99999, 'kg', 5)")
    return db


db = build(N)
products = ProductRepository(db)
print(f"catalogue: {N + 20:,} products\n")
print(f"search 'tom'            {timed(lambda: products.search('tom')):8.2f} ms")
print(f"search 'palm oil'       {timed(lambda: products.search('palm oil')):8.2f} ms")
print(f"search rare word        {timed(lambda: products.search('dragonfruit')):8.2f} ms   (worst case)")
print(f"search no match         {timed(lambda: products.search('zzzzz')):8.2f} ms   (worst case)")
print(f"browse, first page      {timed(lambda: products.list_active(limit=24)):8.2f} ms")
print(f"browse, Fruits page     {timed(lambda: products.list_active('Fruits', limit=24)):8.2f} ms")

ids = list(range(1, 9))
if hasattr(products, "get_many"):
    print(f"price lookup, 8 items   {timed(lambda: products.get_many(ids)):8.2f} ms  (one query)")
else:
    print(f"price lookup, 8 items   {timed(lambda: [products.get(i) for i in ids]):8.2f} ms  (8 queries)")

page = FakePage(); app = FarmApp(page, db); login(app)
app.tab = 0
print(f"build shop screen       {timed(lambda: app.shop_view(), runs=5):8.2f} ms   ({sum(1 for _ in range(1))} page of {__import__('app.ui', fromlist=['PAGE_SIZE']).PAGE_SIZE} cards)")
from app.seed import seed as _seed
print(f"start-up seed per user  {timed(lambda: _seed(db), runs=5):8.2f} ms   (now once at start-up)")
for i in ids[:5]:
    app.cart.add(i)
print(f"build cart screen (5)   {timed(lambda: app.cart_view(), runs=10):8.2f} ms")
