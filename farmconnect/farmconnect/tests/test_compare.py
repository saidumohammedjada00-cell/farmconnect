import asyncio
import pytest
from app.services.compare import (CompareService, LocalProvider, Offer, SampleProvider,
                                  StoreProvider, TTLCache, merge_and_sort)


class FakeStore(StoreProvider):
    def __init__(self, name, offers=(), delay=0.0, fail=False):
        self.name, self.offers, self.delay, self.fail, self.calls = name, list(offers), delay, fail, 0

    async def search(self, query):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("store down")
        return self.offers


def offer(store, price, qty=1, unit="l", name="Palm oil"):
    return Offer(store, name, price, qty, unit)


def test_merge_sorts_by_price_per_unit_and_marks_cheapest():
    ranked = merge_and_sort([offer("Temu", 4100), offer("Jumia", 3400), offer("Local", 2800)])
    assert [o.store for o in ranked] == ["Local", "Jumia", "Temu"]
    assert [o.cheapest for o in ranked] == [True, False, False]


def test_5_litre_vs_1_litre_compared_fairly():
    ranked = merge_and_sort([offer("A", 3000, 1), offer("B", 12000, 5)])   # B = 2400 per litre
    assert ranked[0].store == "B"


def test_duplicates_removed_keeping_cheapest():
    ranked = merge_and_sort([offer("Jumia", 3500), offer("Jumia", 3400), offer("Jumia", 3600)])
    assert len(ranked) == 1 and ranked[0].price == 3400


def test_merge_empty():
    assert merge_and_sort([]) == []


async def test_stores_run_in_parallel():
    svc = CompareService([FakeStore(n, [offer(n, 100)], delay=0.2) for n in "ABC"], timeout=2)
    start = asyncio.get_running_loop().time()
    result = await svc.compare("palm oil")
    assert asyncio.get_running_loop().time() - start < 0.5      # ~0.2s, not 0.6s
    assert len(result.offers) == 3


async def test_failing_and_slow_stores_are_skipped():
    svc = CompareService([FakeStore("Good", [offer("Good", 100)]),
                          FakeStore("Broken", fail=True),
                          FakeStore("Slow", [offer("Slow", 50)], delay=1)], timeout=0.1)
    result = await svc.compare("palm oil")
    assert [o.store for o in result.offers] == ["Good"]
    assert sorted(result.failed_stores) == ["Broken", "Slow"]


async def test_cache_hit_avoids_second_call_and_partial_results_not_cached():
    store = FakeStore("A", [offer("A", 100)])
    svc = CompareService([store])
    await svc.compare("Palm  Oil"); await svc.compare("palm oil")
    assert store.calls == 1                                  # normalized key -> one call
    bad = FakeStore("B", fail=True)
    svc2 = CompareService([bad])
    await svc2.compare("x"); await svc2.compare("x")
    assert bad.calls == 2


def test_cache_expiry():
    now = [0.0]
    cache = TTLCache(ttl=10, clock=lambda: now[0])
    cache.set("k", 1)
    assert cache.get("k") == 1
    now[0] = 10
    assert cache.get("k") is None


async def test_empty_query_returns_nothing():
    assert (await CompareService([FakeStore("A", [offer("A", 1)])]).compare("   ")).offers == []


async def test_sample_provider_builds_deep_link_and_local_provider(products):
    jumia = await SampleProvider("Jumia").search("Palm oil")
    assert jumia and "jumia.com.ng" in jumia[0].url and "palm+oil" in jumia[0].url
    products.create(None, "Oils", "Palm oil", 2800, "litre", 5)
    result = await CompareService([LocalProvider(products), SampleProvider("Jumia")]).compare("palm oil")
    assert result.offers[0].store == "Local farmers" and result.offers[0].cheapest


async def test_unknown_unit_does_not_break_comparison(products):
    """Bug found in review: a farmer listing in 'basket' crashed the whole search."""
    products.create(None, "Vegetables", "Tomatoes", 9000, "basket", 5)
    products.create(None, "Vegetables", "Tomatoes", 1200, "kg", 5)
    result = await CompareService([LocalProvider(products)]).compare("tomatoes")
    assert len(result.offers) == 2
    assert result.offers[0].unit == "kg" and result.offers[0].cheapest
    assert result.offers[1].unit == "basket" and not result.offers[1].cheapest
