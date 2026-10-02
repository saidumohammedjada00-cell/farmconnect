"""Comparison search: local farmers plus other stores, through one adapter interface.

MVP: external stores use sample data and deep links. In production, replace a sample
adapter with an official API or affiliate-feed adapter. Do not scrape store pages.
"""
import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from urllib.parse import quote_plus

from app.config import CACHE_TTL_SECONDS, STORE_TIMEOUT_SECONDS
from app.repositories import ProductRepository
from app.services.text import normalize_query
from app.services.units import price_per_unit


@dataclass(frozen=True)
class Offer:
    store: str
    name: str
    price: float
    qty: float
    unit: str
    url: str = ""
    per_unit: float = 0.0
    cheapest: bool = False
    comparable: bool = True      # False when the unit is unknown (e.g. "basket")

    def with_per_unit(self) -> "Offer":
        return replace(self, per_unit=price_per_unit(self.price, self.qty, self.unit))


@dataclass
class CompareResult:
    offers: list[Offer] = field(default_factory=list)
    failed_stores: list[str] = field(default_factory=list)


class StoreProvider:
    name = "base"
    cacheable = True      # external stores are cached; local data is always read fresh

    async def search(self, query: str) -> list[Offer]:
        raise NotImplementedError


class LocalProvider(StoreProvider):
    name = "Local farmers"
    cacheable = False     # prices and stock must never be stale

    def __init__(self, products: ProductRepository):
        self.products = products

    async def search(self, query: str) -> list[Offer]:
        rows = self.products.search(query)
        return [Offer(self.name, r["name"], r["price"], 1, r["unit"],
                      url=f"product:{r['id']}") for r in rows]


# Search URLs for each store (deep links). Verify them before you demo.
SEARCH_URLS = {
    "Jumia": "https://www.jumia.com.ng/catalog/?q={q}",
    "Konga": "https://www.konga.com/search?search={q}",
    "Temu": "https://www.temu.com/search_result.html?search_key={q}",
}

# Illustrative sample data for the MVP demo. These are NOT live prices.
SAMPLE_CATALOG = {
    "Jumia": [("Palm oil", 3400, 1, "l"), ("Brown beans", 2900, 1, "kg"),
              ("Rice (local)", 2600, 1, "kg"), ("Honey", 5200, 0.5, "l")],
    "Konga": [("Palm oil", 3250, 1, "l"), ("Brown beans", 3100, 1, "kg"),
              ("Garri", 1500, 1, "kg"), ("Honey", 4900, 0.5, "l")],
    "Temu": [("Palm oil", 4100, 1, "l"), ("Dried pepper", 2300, 0.5, "kg")],
}


class SampleProvider(StoreProvider):
    def __init__(self, name: str, catalog=None):
        self.name = name
        self.catalog = catalog if catalog is not None else SAMPLE_CATALOG.get(name, [])

    async def search(self, query: str) -> list[Offer]:
        q = normalize_query(query)
        link = SEARCH_URLS[self.name].format(q=quote_plus(q)) if self.name in SEARCH_URLS else ""
        return [Offer(self.name, n, p, qty, u, url=link)
                for n, p, qty, u in self.catalog if q and q in normalize_query(n)]


class TTLCache:
    """Time-limited cache with a size cap (least recently used entries are dropped)."""

    def __init__(self, ttl: float = CACHE_TTL_SECONDS, clock=time.monotonic, max_entries: int = 500):
        self.ttl, self.clock, self.max_entries = ttl, clock, max_entries
        self._data: OrderedDict = OrderedDict()

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if self.clock() >= expires:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key, value) -> None:
        self._data[key] = (self.clock() + self.ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:      # an unbounded cache is a memory leak
            self._data.popitem(last=False)


def merge_and_sort(offers: list[Offer]) -> list[Offer]:
    """De-duplicate (store + name + unit), then sort by price per unit. O(n log n).

    Offers with a unit we cannot convert stay visible but are listed after the
    comparable ones and are never marked cheapest.
    """
    seen: dict[tuple, Offer] = {}
    for o in offers:
        try:
            o = o.with_per_unit()
        except ValueError:
            o = replace(o, comparable=False)
        key = (o.store, normalize_query(o.name), o.unit.lower(), o.qty)
        if key not in seen or (o.comparable and o.per_unit < seen[key].per_unit) \
                or (o.comparable and not seen[key].comparable):
            seen[key] = o
    comparable = sorted((o for o in seen.values() if o.comparable), key=lambda o: o.per_unit)
    other = sorted((o for o in seen.values() if not o.comparable), key=lambda o: o.price)
    if comparable:
        comparable[0] = replace(comparable[0], cheapest=True)
    return comparable + other


class CompareService:
    """Share ONE instance between all user sessions so the cache works across users."""

    def __init__(self, providers: list[StoreProvider], cache: TTLCache | None = None,
                 timeout: float = STORE_TIMEOUT_SECONDS):
        self.providers, self.cache, self.timeout = providers, cache or TTLCache(), timeout
        self._inflight: dict[str, asyncio.Future] = {}

    async def _call(self, provider: StoreProvider, query: str):
        return await asyncio.wait_for(provider.search(query), self.timeout)

    async def compare(self, query: str) -> CompareResult:
        q = normalize_query(query)
        if not q:
            return CompareResult()
        task = self._inflight.get(q)
        if task is None:          # identical searches at the same moment share one set of calls
            task = asyncio.ensure_future(self._fetch(q))
            self._inflight[q] = task
            task.add_done_callback(lambda _t, q=q: self._inflight.pop(q, None))
        return await asyncio.shield(task)

    async def _fetch(self, q: str) -> CompareResult:
        offers, failed, pending = [], [], []
        for p in self.providers:
            hit = self.cache.get((p.name, q)) if p.cacheable else None
            if hit is not None:
                offers.extend(hit)
            else:
                pending.append(p)
        # only the stores we do not already have, all in parallel
        results = await asyncio.gather(*[self._call(p, q) for p in pending], return_exceptions=True)
        for p, res in zip(pending, results):
            if isinstance(res, Exception):
                failed.append(p.name)            # one store down must not break the page
            else:
                offers.extend(res)
                if p.cacheable:                  # cache each store on its own; failures are retried alone
                    self.cache.set((p.name, q), res)
        return CompareResult(merge_and_sort(offers), failed)
