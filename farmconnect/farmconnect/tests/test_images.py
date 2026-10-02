from app.services.images import match_image


def test_seller_upload_wins(tmp_path):
    path, alt = match_image("Tomatoes", "Vegetables", "uploads/mine.jpg", tmp_path)
    assert path == "uploads/mine.jpg" and "seller" in alt


def test_stock_photo_and_synonym(tmp_path):
    (tmp_path / "products").mkdir()
    (tmp_path / "products" / "red-bell-pepper.jpg").write_bytes(b"x")
    assert match_image("Tatashe", "Vegetables", assets_dir=tmp_path)[0].endswith("red-bell-pepper.jpg")
    assert match_image("Red bell pepper", "Vegetables", assets_dir=tmp_path)[0].endswith("red-bell-pepper.jpg")


def test_placeholder_never_broken(tmp_path):
    path, alt = match_image("Dragon fruit", "Fruits", assets_dir=tmp_path)
    assert path.endswith("cat_fruit.png") and "coming soon" in alt
    assert match_image("Mystery", None, assets_dir=tmp_path)[0].endswith("cat_default.png")
