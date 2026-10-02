import pytest


def test_register_and_login(users):
    users.create("Ada", "Ada@Mail.com", "password1")
    user = users.authenticate("ada@mail.com", "password1")      # email is case-insensitive
    assert user["name"] == "Ada" and "password_hash" not in user


def test_wrong_password_and_unknown_user(users):
    users.create("Ada", "ada@mail.com", "password1")
    assert users.authenticate("ada@mail.com", "nope-nope") is None
    assert users.authenticate("ghost@mail.com", "password1") is None


def test_duplicate_email(users):
    users.create("Ada", "ada@mail.com", "password1")
    with pytest.raises(ValueError, match="already registered"):
        users.create("Ada 2", "ADA@mail.com", "password2")


@pytest.mark.parametrize("name,email,pw,role", [
    ("", "a@b.com", "password1", "buyer"), ("A", "bad", "password1", "buyer"),
    ("A", "a@b.com", "short", "buyer"), ("A", "a@b.com", "password1", "admin")])
def test_validation(users, name, email, pw, role):
    with pytest.raises(ValueError):
        users.create(name, email, pw, role)


def test_sql_injection_is_harmless(users):
    users.create("Ada", "ada@mail.com", "password1")
    assert users.authenticate("' OR '1'='1", "x") is None
    assert users.authenticate("ada@mail.com' --", "password1") is None
