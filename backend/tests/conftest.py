import os
os.environ.update(DATABASE_URL=os.environ.get("TEST_DATABASE_URL", "postgresql://noel:noel@localhost/noel_test"), APP_SECRET="s"*48, ADMIN_USER="ali", ADMIN_PASSWORD="motdepasse", STAFF_PIN="424242",
                  ALLOWED_ORIGINS="http://localhost:8099", GAME_START="2026-12-01", GAME_END="2026-12-31", VERIFY_MODE="console")
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from noel_app import game
from noel_app.db import Base, engine
from noel_app.main import app


class Clock:
    value = datetime(2026, 12, 10, 12, 0, tzinfo=game.PARIS)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    c.value = datetime(2026, 12, 10, 12, 0, tzinfo=game.PARIS)
    monkeypatch.setattr(game, "now", lambda: c.value)
    return c


@pytest.fixture
def codes(monkeypatch):
    sent = {}
    monkeypatch.setattr(game.notify, "send_code", lambda contact, kind, code, lang: sent.__setitem__(contact, code))
    return sent


@pytest.fixture(autouse=True)
def fresh():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
