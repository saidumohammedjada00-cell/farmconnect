"""Match every product to an image. Paths are relative to the assets folder."""
from pathlib import Path

from app.config import ASSETS_DIR
from app.services.text import canonical_slug

PLACEHOLDERS = {"Vegetables": "cat_veg.png", "Fruits": "cat_fruit.png",
                "Tubers": "cat_tuber.png", "Grains": "cat_grain.png"}


def match_image(name: str, category: str | None = None,
                seller_upload: str | None = None,
                assets_dir: Path = ASSETS_DIR) -> tuple[str, str]:
    """Return (image_path, alt_text). Seller photo > stock photo > category placeholder."""
    if seller_upload:
        return seller_upload, f"Photo of {name} from the seller"
    slug = canonical_slug(name)
    stock = Path("products") / f"{slug}.jpg"
    if (assets_dir / stock).exists():
        return str(stock), f"Fresh {name}"
    placeholder = PLACEHOLDERS.get(category or "", "cat_default.png")
    return str(Path("products") / placeholder), f"{name} (photo coming soon)"
