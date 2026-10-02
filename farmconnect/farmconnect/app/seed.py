"""Sample catalogue: 20 farm products."""
from app.repositories import ProductRepository, UserRepository
from app.db import Database

PRODUCTS = [  # name, category, price, unit, qty
    ("Tomatoes", "Vegetables", 1200, "kg", 50), ("Red bell pepper", "Vegetables", 1500, "kg", 30),
    ("Scotch bonnet", "Vegetables", 2000, "kg", 20), ("Onions", "Vegetables", 900, "kg", 80),
    ("Ugu leaves", "Vegetables", 500, "piece", 60), ("Okra", "Vegetables", 800, "kg", 40),
    ("Spinach", "Vegetables", 400, "piece", 60), ("Yam", "Tubers", 3500, "piece", 40),
    ("Sweet potato", "Tubers", 1000, "kg", 50), ("Cassava", "Tubers", 700, "kg", 70),
    ("Plantain", "Fruits", 600, "piece", 90), ("Banana", "Fruits", 500, "kg", 60),
    ("Pineapple", "Fruits", 1200, "piece", 30), ("Watermelon", "Fruits", 2500, "piece", 25),
    ("Oranges", "Fruits", 800, "kg", 100), ("Brown beans", "Grains", 2500, "kg", 120),
    ("Maize", "Grains", 700, "kg", 150), ("Rice (local)", "Grains", 2200, "kg", 200),
    ("Palm oil", "Oils", 2800, "litre", 60), ("Honey", "Other", 4500, "litre", 25),
]


def seed(db: Database) -> None:
    users = UserRepository(db)
    try:
        farmer_id = users.create("Mama Ngozi", "ngozi@farm.test", "farmpass123", "farmer")
    except ValueError:
        return                                   # already seeded
    with db.connect() as c:
        sid = c.execute("INSERT INTO seller_profiles (user_id, farm_name, location, verified) "
                        "VALUES (?,?,?,1)", (farmer_id, "Ngozi Farms", "Abuja")).lastrowid
    products = ProductRepository(db)
    for name, cat, price, unit, qty in PRODUCTS:
        products.create(sid, cat, name, price, unit, qty, location="Abuja")
