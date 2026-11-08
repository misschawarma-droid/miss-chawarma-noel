"""Réglages lus dans l'environnement. Aucun secret par défaut."""
import os
from dataclasses import dataclass, field
from datetime import date


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante : {name}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: _required("DATABASE_URL").replace("postgres://", "postgresql://", 1))
    app_secret: str = field(default_factory=lambda: _required("APP_SECRET"))
    admin_user: str = field(default_factory=lambda: _required("ADMIN_USER"))
    admin_password: str = field(default_factory=lambda: _required("ADMIN_PASSWORD"))
    staff_pin: str = field(default_factory=lambda: _required("STAFF_PIN"))
    allowed_origins: tuple = field(default_factory=lambda: tuple(o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "https://misschawarma.fr,https://www.misschawarma.fr").split(",") if o.strip()))
    game_start: date = field(default_factory=lambda: date.fromisoformat(os.environ.get("GAME_START", "2026-12-01")))
    game_end: date = field(default_factory=lambda: date.fromisoformat(os.environ.get("GAME_END", "2026-12-31")))
    verify_mode: str = field(default_factory=lambda: os.environ.get("VERIFY_MODE", "on"))
    twilio_sid: str = field(default_factory=lambda: os.environ.get("TWILIO_ACCOUNT_SID", ""))
    twilio_token: str = field(default_factory=lambda: os.environ.get("TWILIO_AUTH_TOKEN", ""))
    twilio_from: str = field(default_factory=lambda: os.environ.get("TWILIO_FROM", ""))
    resend_key: str = field(default_factory=lambda: os.environ.get("RESEND_API_KEY", ""))
    resend_from: str = field(default_factory=lambda: os.environ.get("RESEND_FROM", "Miss Chawarma <noel@misschawarma.fr>"))
    max_plays_per_ip_per_day: int = 60       # le Wi-Fi du restaurant partage une seule adresse
    max_codes_per_contact_per_hour: int = 3
    max_codes_per_ip_per_hour: int = 20
    max_codes_per_day: int = 1000            # plafond global : protège le budget SMS
    max_pin_failures: int = 5


settings = Settings()
if settings.verify_mode not in {"on", "off", "console"}:
    raise RuntimeError("VERIFY_MODE doit valoir on, off ou console")
if len(settings.staff_pin) != 6 or not settings.staff_pin.isdigit():
    raise RuntimeError("STAFF_PIN doit contenir exactement 6 chiffres")
