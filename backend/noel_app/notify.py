"""Envoi du code de vérification."""
import logging
import os

import httpx

from .config import settings

log = logging.getLogger("noel")

TEXT = {
    "fr": "Miss Chawarma : votre code pour la roue de Noël est {code}. Il expire dans 10 minutes.",
    "en": "Miss Chawarma: your Christmas wheel code is {code}. It expires in 10 minutes.",
}
SUBJECT = {"fr": "Votre code Miss Chawarma", "en": "Your Miss Chawarma code"}


class SendError(Exception):
    pass


def send_code(contact: str, kind: str, code: str, lang: str) -> None:
    body = TEXT.get(lang, TEXT["fr"]).format(code=code)
    if settings.verify_mode == "console":
        log.warning("[VERIFY_MODE=console] code pour %s : %s", contact, code)
        return
    try:
        if kind == "phone":
            _sms(contact, body)
        else:
            _email(contact, body, SUBJECT.get(lang, SUBJECT["fr"]))
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
        log.error("Envoi du code impossible (%s) : %s", kind, status)
        raise SendError from exc


def _sms(to: str, body: str) -> None:
    if not (settings.twilio_sid and settings.twilio_token and settings.twilio_from):
        raise SendError("Twilio non configuré")
    r = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
        auth=(settings.twilio_sid, settings.twilio_token),
        data={"To": to, "From": settings.twilio_from, "Body": body},
        timeout=10,
    )
    r.raise_for_status()


def _email(to: str, body: str, subject: str) -> None:
    key = os.environ.get("BREVO_API_KEY", "").strip()
    sender = os.environ.get("BREVO_SENDER_EMAIL", "").strip()
    if not (key and sender):
        raise SendError("Brevo non configuré")
    r = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": key, "accept": "application/json"},
        json={
            "sender": {"name": "Miss Chawarma", "email": sender},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
        timeout=10,
    )
    r.raise_for_status()