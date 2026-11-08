from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import func, select

from noel_app import game
from noel_app.db import SessionLocal
from noel_app.models import GoldAward, Play, Player
from noel_app.prizes import REGULAR, gold_for

PHONE = "06 12 34 56 78"


def join(client, codes, contact=PHONE, marketing=False):
    r = client.post("/api/request-code", json={"contact": contact})
    assert r.status_code == 200, r.text
    code = codes[game.normalize_contact(contact)[0]]
    return client.post("/api/play", json={"contact": contact, "otp": code, "accept_rules": True, "marketing": marketing})


def hdr(tok):
    return {"X-Noel-Token": tok}


def test_contact_formats():
    assert game.normalize_contact("06 12 34 56 78") == ("+33612345678", "phone")
    assert game.normalize_contact("+33 7.12.34.56.78") == ("+33712345678", "phone")
    assert game.normalize_contact("0033612345678")[0] == "+33612345678"
    assert game.normalize_contact("A.b.C+promo@GMAIL.com") == ("abc@gmail.com", "email")


def test_rejects_premium_and_foreign(client, clock, codes):
    for bad in ("0899123456", "+21612345678", "+447911123456", "pas-un-contact"):
        assert client.post("/api/request-code", json={"contact": bad}).status_code == 422


def test_full_flow_and_one_per_day(client, clock, codes):
    r = join(client, codes)
    assert r.status_code == 200
    tok, ticket = r.json()["token"], r.json()["ticket"]
    assert ticket["code"].startswith("NOEL-")
    s = client.get("/api/state", headers=hdr(tok)).json()
    assert s["ticket_today"]["code"] == ticket["code"] and s["known"]
    assert client.post("/api/play", json={}, headers=hdr(tok)).json()["detail"] == "already_played"
    clock.value += timedelta(days=1)
    r2 = client.post("/api/play", json={}, headers=hdr(tok))
    assert r2.status_code == 200 and r2.json()["ticket"]["code"] != ticket["code"]
    assert sum(1 for d in client.get("/api/state", headers=hdr(tok)).json()["days"] if d["ticket"]) == 2


def test_otp_required_wrong_and_locked(client, clock, codes):
    assert client.post("/api/play", json={"contact": PHONE, "accept_rules": True}).json()["detail"] == "code_required"
    client.post("/api/request-code", json={"contact": PHONE})
    good = codes["+33612345678"]
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/play", json={"contact": PHONE, "otp": wrong, "accept_rules": True}).json()["detail"] == "code_wrong"
    assert client.post("/api/play", json={"contact": PHONE, "otp": good, "accept_rules": True}).json()["detail"] == "code_locked"


def test_otp_cannot_be_reused_and_expires(client, clock, codes):
    client.post("/api/request-code", json={"contact": PHONE})
    code = codes["+33612345678"]
    assert client.post("/api/play", json={"contact": PHONE, "otp": code, "accept_rules": True}).status_code == 200
    assert client.post("/api/play", json={"contact": PHONE, "otp": code, "accept_rules": True}).json()["detail"] == "code_expired"
    client.post("/api/request-code", json={"contact": "0711111111"})
    clock.value += timedelta(minutes=11)
    assert client.post("/api/play", json={"contact": "0711111111", "otp": codes["+33711111111"], "accept_rules": True}).json()["detail"] == "code_expired"


def test_code_rate_limit(client, clock, codes):
    for _ in range(3):
        assert client.post("/api/request-code", json={"contact": PHONE}).status_code == 200
    assert client.post("/api/request-code", json={"contact": PHONE}).json()["detail"] == "too_many_codes"


def test_new_device_cannot_replay_same_day(client, clock, codes):
    first = join(client, codes)
    assert first.status_code == 200
    second = join(client, codes)
    assert second.status_code == 409 and second.json()["detail"] == "already_played"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Play)) == 1


def test_rules_required(client, clock, codes):
    client.post("/api/request-code", json={"contact": PHONE})
    assert client.post("/api/play", json={"contact": PHONE, "otp": codes["+33612345678"]}).json()["detail"] == "rules_required"


def test_contact_only_stored_with_consent(client, clock, codes):
    join(client, codes, PHONE, marketing=False)
    join(client, codes, "0712345678", marketing=True)
    with SessionLocal() as db:
        rows = {p.contact for p in db.scalars(select(Player))}
    assert rows == {None, "+33712345678"}


def test_game_window(client, clock, codes):
    clock.value = datetime(2026, 11, 30, 23, 59, tzinfo=game.PARIS)
    assert client.get("/api/state").json()["status"] == "before"
    assert client.post("/api/request-code", json={"contact": PHONE}).json()["detail"] == "game_closed"
    clock.value = datetime(2026, 12, 31, 23, 59, tzinfo=game.PARIS)
    assert client.get("/api/state").json()["status"] == "open"
    tok = join(client, codes).json()
    clock.value = datetime(2027, 1, 1, 0, 1, tzinfo=game.PARIS)
    assert client.get("/api/state").json()["status"] == "ended"
    assert client.post("/api/play", json={}, headers=hdr(tok["token"])).json()["detail"] == "game_closed"
    clock.value = datetime(2027, 1, 1, 3, 1, tzinfo=game.PARIS)
    assert client.post("/api/redeem", json={"code": tok["ticket"]["code"], "pin": "424242"}).json()["detail"] == "expired"


def test_redeem_during_new_year_night(client, clock, codes):
    clock.value = datetime(2026, 12, 31, 22, 0, tzinfo=game.PARIS)
    code = join(client, codes).json()["ticket"]["code"]
    clock.value = datetime(2027, 1, 1, 1, 30, tzinfo=game.PARIS)
    assert client.post("/api/redeem", json={"code": code, "pin": "424242"}).status_code == 200


def test_email_rejects_markup_and_formula(client, clock, codes):
    for bad in ("<img/src=x>@evil.fr", "=cmd@evil.fr", "+x@evil.fr", "a@evil", "a b@c.fr"):
        assert client.post("/api/request-code", json={"contact": bad}).status_code == 422


def test_daily_code_cap(client, clock, codes, monkeypatch):
    monkeypatch.setattr(game, "settings", __import__("dataclasses").replace(game.settings, max_codes_per_day=1))
    assert client.post("/api/request-code", json={"contact": PHONE}).status_code == 200
    assert client.post("/api/request-code", json={"contact": "0711111111"}).json()["detail"] == "too_many_codes"


def test_admin_login_throttle(client):
    from noel_app.admin import _login_failures
    _login_failures.clear()
    for _ in range(8):
        client.post("/admin/login", data={"username": "ali", "password": "faux"}, follow_redirects=False)
    assert client.post("/admin/login", data={"username": "ali", "password": "motdepasse"}, follow_redirects=False).status_code == 400
    _login_failures.clear()


def test_redeem_once_and_pin_lock(client, clock, codes):
    t = join(client, codes).json()["ticket"]["code"]
    for _ in range(5):
        assert client.post("/api/redeem", json={"code": t, "pin": "000000"}).json()["detail"] == "pin_wrong"
    assert client.post("/api/redeem", json={"code": t, "pin": "424242"}).json()["detail"] == "pin_locked"
    t2 = join(client, codes, "0712345678").json()["ticket"]["code"]
    r = client.post("/api/redeem", json={"code": t2, "pin": "424242"})
    assert r.status_code == 200 and r.json()["ticket"]["redeemed"]
    assert client.post("/api/redeem", json={"code": t2, "pin": "424242"}).json()["detail"] == "already_redeemed"
    assert client.post("/api/redeem", json={"code": "NOEL-XXXXXX", "pin": "424242"}).json()["detail"] == "unknown_code"


def _make_player(db, n):
    p = Player(contact_hash=f"h{n}", contact_type="phone", token_hash=f"t{n}", created_at=game.now(), lang="fr")
    db.add(p)
    return p


def test_gold_unique_under_concurrency(clock, monkeypatch):
    monkeypatch.setattr(game, "gold_probability", lambda h: 1.0)
    with SessionLocal() as db:
        tokens = []
        for n in range(24):
            tok = f"token{n}"
            db.add(Player(contact_hash=f"h{n}", contact_type="phone", token_hash=game.sha(tok), created_at=game.now(), lang="fr"))
            tokens.append(tok)
        db.commit()

    def go(tok):
        with SessionLocal() as db:
            return game.play(db, tok, None, None, False, False, "fr", "1.1.1.1")["ticket"]["is_gold"]

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(go, tokens))
    assert sum(res) == 1 and len(res) == 24
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GoldAward)) == 1


def test_double_click_gives_one_play(clock):
    with SessionLocal() as db:
        db.add(Player(contact_hash="h", contact_type="phone", token_hash=game.sha("tok"), created_at=game.now(), lang="fr"))
        db.commit()

    def go(_):
        with SessionLocal() as db:
            try:
                return game.play(db, "tok", None, None, False, False, "fr", "1.1.1.1") and "ok"
            except game.HTTPException as e:
                return e.detail

    with ThreadPoolExecutor(8) as ex:
        res = Counter(ex.map(go, range(16)))
    assert res == {"ok": 1, "already_played": 15}


def test_redeem_race(clock, client, codes):
    code = join(client, codes).json()["ticket"]["code"]

    def go(_):
        with SessionLocal() as db:
            try:
                game.redeem(db, code, "424242")
                return "ok"
            except game.HTTPException as e:
                return e.detail

    with ThreadPoolExecutor(8) as ex:
        res = Counter(ex.map(go, range(16)))
    assert res == {"ok": 1, "already_redeemed": 15}


def test_distribution_and_calendar():
    c = Counter(game._draw_regular().id for _ in range(200000))
    for p in REGULAR:
        assert abs(c[p.id] / 2000 - p.weight) < 0.5
    from datetime import date
    assert gold_for(date(2026, 12, 24)).fr == "Le Mezze Royal offert"
    assert all(gold_for(date(2026, 12, d)).value_cents > 0 for d in range(1, 32))


def test_admin_requires_login_and_recap(client, clock, codes):
    join(client, codes)
    assert client.get("/admin/recap", follow_redirects=False).status_code in (302, 303)
    assert client.post("/admin/login", data={"username": "ali", "password": "faux"}, follow_redirects=False).status_code == 400
    assert client.post("/admin/login", data={"username": "ali", "password": "motdepasse"}, follow_redirects=False).status_code == 302
    r = client.get("/admin/recap")
    assert r.status_code == 200 and "Tours joués" in r.text
    assert client.get("/admin/play/list").status_code == 200
    assert client.get("/admin/player/list").status_code == 200


def test_purge(client, clock, codes):
    join(client, codes, PHONE, marketing=False)
    join(client, codes, "0712345678", marketing=True)
    from noel_app.purge import main
    main()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Player)) == 1
        plays = list(db.scalars(select(Play)))
        assert len(plays) == 2 and all(p.ip is None for p in plays) and sum(p.player_id is None for p in plays) == 1
