# FarmConnect (CSE 720 coursework)

Farm-produce marketplace in Python + Flet. Buyers search once and see local farmers' prices
beside Jumia, Konga and Temu prices, compared per kg / litre / piece.

## Run
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py                  # desktop window
flet run --web main.py          # in the browser
flet run --android main.py      # phone, with the Flet app installed
```
Sample login (farmer): `ngozi@farm.test` / `farmpass123`. Or create your own account.

## Test
```bash
pytest -q                       # 157 tests: logic, WCAG, security, efficiency
pytest --cov=app                # coverage report
```

## Layout
| Path | Purpose |
|---|---|
| `main.py` | Entry point, theme, database start-up |
| `app/ui.py` | Flet screens: login, shop, results, cart, checkout, account, farmer form |
| `app/repositories.py` | Data access layer (parameterized SQL only) |
| `app/db.py`, `app/seed.py` | Schema and 20 sample products |
| `app/security.py` | scrypt hashing, validation, login lockout |
| `app/uploads.py`, `app/seclog.py` | ClamAV-scanned image uploads, security event log |
| `app/services/compare.py` | Store adapters, parallel search, cache, merge and sort |
| `app/services/units.py`, `cart.py`, `images.py`, `text.py` | Unit prices, cart, image matching, search helpers |
| `tests/` | Unit and smoke tests |

## Product images
Put one JPG per product in `assets/products/` named by slug (`tomatoes.jpg`, `palm-oil.jpg`).
Missing images fall back to a 🌱 placeholder, so nothing ever shows broken.
Use only photos you may legally reuse (your own, Unsplash, Pexels) and keep the credit.

## External stores
`SampleProvider` returns illustrative sample prices (NOT live) plus a real search link per store.
To go live, write a new class with `async def search(query) -> list[Offer]` that calls an
official API or affiliate feed, and swap it into `CompareService` in `app/ui.py`.
Do not scrape store pages. Check the three search URLs in `SEARCH_URLS` before your demo.

## Known limits of the MVP
- "Card or transfer" is recorded but Paystack is not wired yet (Phase 4).
- No order-status screen for farmers yet.

## Accessibility (WCAG 2.2 AA)
Automated checks live in `tests/test_accessibility.py` (contrast, names and labels, target size,
text scaling). Still test by hand: TalkBack (Android), VoiceOver (iOS), keyboard-only on web,
200% browser zoom, and a phone in bright sunlight.

See `SECURITY.md` for the minimum security standard (OWASP Top 10:2025 and ClamAV).

## Performance
Measured with `python scripts/benchmark.py 200000` (Python-side timings on a development machine;
a phone will be slower, and network transfer is not included).

| Operation (200,000 products) | Before | After |
|---|---|---|
| Browse first page | 38.8 ms | 0.3 ms |
| Search, common word | 53.0 ms | 2.6 ms |
| Search, rare word or no match (worst case) | 88 ms | 15 ms |
| Cards built per screen | 100 | 24, "Show more" for the rest |
| Database setup + seeding per visitor | 30 ms | once at start-up |
| Tap "Add to cart" | rebuilds the whole screen | updates the cart badge only |

What was added: indexes for browse and category pages, trigram full-text search (with automatic
fallback to LIKE), paged product grid with the category filter in SQL, WAL mode, one shared and
size-capped comparison cache (external stores cached per store, local prices always fresh,
identical simultaneous searches share one request), and batch product lookup in the cart.

Trade-off: the search index makes the database about 2.3x larger (58 MB vs 25 MB at 200k products).
Do not replace the `IN (subquery)` in `ProductRepository.search` with a JOIN: it took 7 seconds on rare words.

Also: uploads create a 320 px thumbnail (`thumbs/`) for the product grid, and searches are limited to
10 per minute per user (shared across sessions) to protect the external stores and hosting costs.
