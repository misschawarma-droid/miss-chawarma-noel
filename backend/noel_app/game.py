"""Règles du jeu. Tout le tirage se fait ici, jamais dans le navigateur."""
import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import notify
from .config import settings
from .models import GoldAward, OtpChallenge, Play, Player
from .prizes import REGULAR, Prize, gold_for, gold_probability

PARIS = ZoneInfo("Europe/Paris")
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_rng = secrets.SystemRandom()


def now() -> datetime:
    return datetime.now(PARIS)


def client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "true-client-ip"):
        if request.headers.get(header):
            return request.headers[header][:64]
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown"))[:64]


def fail(status: int, code: str):
    raise HTTPException(status_code=status, detail=code)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def keyed(value: str) -> str:
    return hmac.new(settings.app_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def normalize_contact(raw: str) -> tuple[str, str]:
    """Renvoie (contact, type). Mobiles français ou emails uniquement."""
    value = (raw or "").strip()
    if "@" in value:
        email = value.lower()
        if len(email) > 254 or not re.fullmatch(r"[a-z0-9_][a-z0-9._%+-]*@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", email):
            fail(422, "invalid_contact")
        local, domain = email.rsplit("@", 1)
        if domain in {"gmail.com", "googlemail.com"}:
            local = local.split("+", 1)[0].replace(".", "")
            domain = "gmail.com"
        return f"{local}@{domain}", "email"
    digits = re.sub(r"[\s.\-()]", "", value)
    if digits.startswith("0033"):
        digits = "+33" + digits[4:]
    elif digits.startswith("33") and len(digits) == 11:
        digits = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        digits = "+33" + digits[1:]
    if not re.fullmatch(r"\+33[67]\d{8}", digits):
        fail(422, "invalid_contact")
    return digits, "phone"


def game_status(today: date) -> str:
    if today < settings.game_start:
        return "before"
    if today > settings.game_end:
        return "ended"
    return "open"


def ticket_json(p: Play) -> dict:
    return {"code": p.code, "prize_id": p.prize_id, "is_gold": p.is_gold, "label_fr": p.label_fr, "label_en": p.label_en,
            "day": p.game_day.isoformat(), "redeemed": p.redeemed_at is not None, "valid_until": settings.game_end.isoformat()}


def player_from_token(db: Session, token: str | None) -> Player | None:
    if not token:
        return None
    return db.scalar(select(Player).where(Player.token_hash == sha(token)))


def state(db: Session, token: str | None) -> dict:
    current = now()
    today = current.date()
    player = player_from_token(db, token)
    tickets = {}
    if player:
        tickets = {p.game_day: p for p in db.scalars(select(Play).where(Play.player_id == player.id))}
    gold = gold_for(today)
    gold_taken = db.get(GoldAward, today) is not None
    days, cursor = [], settings.game_start
    while cursor <= settings.game_end:
        kind = "today" if cursor == today else "past" if cursor < today else "future"
        days.append({"date": cursor.isoformat(), "kind": kind, "ticket": ticket_json(tickets[cursor]) if cursor in tickets else None})
        cursor += timedelta(days=1)
    return {
        "status": game_status(today), "today": today.isoformat(), "start": settings.game_start.isoformat(), "end": settings.game_end.isoformat(),
        "verify": settings.verify_mode != "off",
        "gold": {"label_fr": gold.fr, "label_en": gold.en, "taken": gold_taken},
        "odds": [{"id": p.id, "label_fr": p.fr, "label_en": p.en, "pct": p.weight} for p in REGULAR],
        "known": player is not None,
        "ticket_today": ticket_json(tickets[today]) if today in tickets else None,
        "days": days,
    }


def request_code(db: Session, raw_contact: str, lang: str, ip: str) -> dict:
    if settings.verify_mode == "off":
        return {"sent": False}
    if game_status(now().date()) != "open":
        fail(409, "game_closed")
    contact, kind = normalize_contact(raw_contact)
    ch = keyed(contact)
    since = now() - timedelta(hours=1)
    n_contact = db.scalar(select(func.count()).select_from(OtpChallenge).where(OtpChallenge.contact_hash == ch, OtpChallenge.created_at > since))
    n_ip = db.scalar(select(func.count()).select_from(OtpChallenge).where(OtpChallenge.ip == ip, OtpChallenge.created_at > since))
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    n_day = db.scalar(select(func.count()).select_from(OtpChallenge).where(OtpChallenge.created_at >= midnight))
    if n_contact >= settings.max_codes_per_contact_per_hour or n_ip >= settings.max_codes_per_ip_per_hour or n_day >= settings.max_codes_per_day:
        fail(429, "too_many_codes")
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OtpChallenge(contact_hash=ch, code_hash=keyed(ch + code), expires_at=now() + timedelta(minutes=10), ip=ip, created_at=now())
    db.add(challenge)
    db.commit()
    try:
        notify.send_code(contact, kind, code, lang)
    except notify.SendError:
        db.delete(challenge)
        db.commit()
        fail(502, "send_failed")
    return {"sent": True, "channel": kind}


def _check_otp(db: Session, contact_hash: str, otp: str | None) -> None:
    if not otp:
        fail(422, "code_required")
    challenge = db.scalar(select(OtpChallenge).where(OtpChallenge.contact_hash == contact_hash, OtpChallenge.used.is_(False))
                          .order_by(OtpChallenge.created_at.desc()).limit(1).with_for_update())
    if not challenge or challenge.expires_at < now():
        fail(422, "code_expired")
    if challenge.attempts >= 5:
        fail(429, "code_locked")
    if not hmac.compare_digest(challenge.code_hash, keyed(contact_hash + otp.strip())):
        challenge.attempts += 1
        db.commit()
        fail(422, "code_wrong")
    challenge.used = True


def _resolve_player(db: Session, token, raw_contact, otp, marketing, lang):
    """Renvoie (joueur, nouveau jeton ou None)."""
    player = player_from_token(db, token)
    if player:
        return player, None
    if token and not raw_contact:
        fail(401, "session_lost")
    if not raw_contact:
        fail(422, "contact_required")
    contact, kind = normalize_contact(raw_contact)
    ch = keyed(contact)
    if settings.verify_mode != "off":
        _check_otp(db, ch, otp)
    player = db.scalar(select(Player).where(Player.contact_hash == ch))
    if player is not None and settings.verify_mode == "off":
        # Sans vérification, connaître un numéro ne doit pas donner accès aux cadeaux de quelqu'un.
        fail(409, "use_first_device")
    new_token = secrets.token_urlsafe(32)
    if player is None:
        player = Player(contact_hash=ch, contact_type=kind, lang=lang, token_hash=sha(new_token), created_at=now())
        db.add(player)
    else:
        player.token_hash = sha(new_token)
    if marketing and not player.marketing_consent:
        player.marketing_consent = True
        player.contact = contact
        player.consent_at = now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        fail(409, "try_again")
    return player, new_token


def _draw_regular() -> Prize:
    return _rng.choices(REGULAR, weights=[p.weight for p in REGULAR], k=1)[0]


def _new_code() -> str:
    return "NOEL-" + "".join(secrets.choice(ALPHABET) for _ in range(6))


def play(db: Session, token, raw_contact, otp, accept_rules, marketing, lang, ip) -> dict:
    current = now()
    today = current.date()
    if game_status(today) != "open":
        fail(409, "game_closed")
    n_ip = db.scalar(select(func.count()).select_from(Play).where(Play.game_day == today, Play.ip == ip))
    if n_ip >= settings.max_plays_per_ip_per_day:
        fail(429, "too_many_plays")
    if not token and not accept_rules:
        fail(422, "rules_required")
    player, new_token = _resolve_player(db, token, raw_contact, otp, marketing, lang)

    prize = _draw_regular()
    row = Play(player_id=player.id, game_day=today, prize_id=prize.id, label_fr=prize.fr, label_en=prize.en, value_cents=prize.value_cents,
               is_gold=False, code=_new_code(), ip=ip, created_at=current)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Déjà joué aujourd'hui (ou collision de code, assez rare pour redemander un essai).
        db.commit()   # conserve le code à usage unique consommé et le jeton éventuel
        existing = db.scalar(select(Play).where(Play.player_id == player.id, Play.game_day == today))
        if existing is None:
            fail(409, "try_again")
        raise HTTPException(status_code=409, detail="already_played", headers={"X-Noel-Token": new_token} if new_token else None)

    if _rng.random() < gold_probability(current.hour):
        try:
            with db.begin_nested():
                db.add(GoldAward(game_day=today, created_at=current))
                db.flush()
        except IntegrityError:
            pass    # le lot en or du jour vient d'être pris : on garde le lot normal
        else:
            gold = gold_for(today)
            row.prize_id, row.label_fr, row.label_en, row.value_cents, row.is_gold = "gold", gold.fr, gold.en, gold.value_cents, True
    db.commit()
    return {"ticket": ticket_json(row), "token": new_token}


def redeem(db: Session, code: str, pin: str) -> dict:
    code = (code or "").strip().upper()
    # Le 31 décembre tombe un jeudi : le restaurant ferme à 2 h, on laisse jusqu'à 3 h pour valider.
    if now() > datetime.combine(settings.game_end + timedelta(days=1), time(3, 0), PARIS):
        fail(410, "expired")
    play_row = db.scalar(select(Play).where(Play.code == code))
    if play_row is None:
        fail(404, "unknown_code")
    if play_row.pin_failures >= settings.max_pin_failures:
        fail(423, "pin_locked")
    if not hmac.compare_digest((pin or "").encode(), settings.staff_pin.encode()):
        db.execute(update(Play).where(Play.id == play_row.id).values(pin_failures=Play.pin_failures + 1))
        db.commit()
        fail(403, "pin_wrong")
    done = db.execute(update(Play).where(Play.id == play_row.id, Play.redeemed_at.is_(None)).values(redeemed_at=now()))
    db.commit()
    if done.rowcount == 0:
        fail(409, "already_redeemed")
    db.refresh(play_row)
    return {"ticket": ticket_json(play_row)}
