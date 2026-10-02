"""Text helpers shared by search and image matching."""
import re

# Local names -> canonical product slug
SYNONYMS = {
    "tatashe": "red-bell-pepper",
    "ata rodo": "scotch-bonnet",
    "ugu": "ugu-leaves",
    "efo": "spinach",
    "garri": "cassava",
    "tomato": "tomatoes",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def normalize_query(query: str) -> str:
    """Lowercase, collapse spaces, and drop characters that are not letters, digits, or spaces."""
    q = re.sub(r"[^a-z0-9 ]+", " ", (query or "").lower())
    return re.sub(r"\s+", " ", q).strip()


def canonical_slug(name: str) -> str:
    """Return the canonical slug for a product name, using synonyms."""
    return SYNONYMS.get(normalize_query(name), slugify(name))
