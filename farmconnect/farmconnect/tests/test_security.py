from app.security import hash_password, validate_email, validate_password, verify_password


def test_hash_is_salted_and_verifies():
    h1, h2 = hash_password("secret123"), hash_password("secret123")
    assert h1 != h2                       # different salt each time
    assert verify_password("secret123", h1)
    assert not verify_password("wrong-pass", h1)


def test_verify_rejects_malformed_hash():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "md5$aa$bb")


def test_validators():
    assert validate_email("a@b.com")
    assert not validate_email("a@b") and not validate_email("") and not validate_email(None)
    assert validate_password("12345678") and not validate_password("1234567")
