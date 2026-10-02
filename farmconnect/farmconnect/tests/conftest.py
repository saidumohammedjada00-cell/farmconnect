import pytest
from app.db import Database
from app.repositories import OrderRepository, ProductRepository, UserRepository


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.init()
    return d


@pytest.fixture
def users(db):
    return UserRepository(db)


@pytest.fixture
def products(db):
    return ProductRepository(db)


@pytest.fixture
def orders(db):
    return OrderRepository(db)
