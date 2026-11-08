"""Back-office : suivi du jeu pour Ali."""
import hmac
import time
from collections import defaultdict
from pathlib import Path

from fastapi import Request
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import case, func, select

from .config import settings
from .game import client_ip
from .db import SessionLocal, engine
from .models import Play, Player
from .prizes import REGULAR


_login_failures = defaultdict(list)
MAX_LOGIN_FAILURES, LOGIN_WINDOW_SECONDS = 8, 900


class Auth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        ip, clock = client_ip(request), time.monotonic()
        recent = [t for t in _login_failures[ip] if clock - t < LOGIN_WINDOW_SECONDS]
        _login_failures[ip] = recent
        if len(recent) >= MAX_LOGIN_FAILURES:
            return False
        form = await request.form()
        ok_user = hmac.compare_digest(str(form.get("username", "")).encode(), settings.admin_user.encode())
        ok_pass = hmac.compare_digest(str(form.get("password", "")).encode(), settings.admin_password.encode())
        if ok_user and ok_pass:
            _login_failures.pop(ip, None)
            request.session["noel_admin"] = True
            return True
        recent.append(clock)
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("noel_admin"))


class PlayAdmin(ModelView, model=Play):
    name, name_plural, icon = "Partie", "Parties", "fa-solid fa-gift"
    can_create = can_edit = can_delete = False
    column_list = [Play.game_day, Play.code, Play.label_fr, Play.is_gold, Play.redeemed_at, Play.created_at]
    column_labels = {Play.game_day: "Jour", Play.code: "Code", Play.label_fr: "Lot", Play.is_gold: "Lot en or", Play.redeemed_at: "Servi le", Play.created_at: "Joué le"}
    column_searchable_list = [Play.code]
    column_sortable_list = [Play.game_day, Play.created_at, Play.redeemed_at, Play.is_gold]
    column_default_sort = [(Play.created_at, True)]
    column_details_exclude_list = [Play.ip, Play.player_id]
    column_export_list = [Play.game_day, Play.code, Play.label_fr, Play.is_gold, Play.redeemed_at]
    page_size = 50


class PlayerAdmin(ModelView, model=Player):
    name, name_plural, icon = "Contact", "Contacts", "fa-solid fa-address-book"
    can_create = can_edit = can_delete = False
    column_list = [Player.contact, Player.contact_type, Player.marketing_consent, Player.consent_at, Player.created_at]
    column_labels = {Player.contact: "Contact (si accord)", Player.contact_type: "Type", Player.marketing_consent: "Accepte les offres", Player.consent_at: "Accord le", Player.created_at: "Inscrit le"}
    column_details_exclude_list = [Player.contact_hash, Player.token_hash]
    column_export_list = [Player.contact, Player.contact_type, Player.consent_at]
    column_sortable_list = [Player.created_at, Player.marketing_consent]
    column_default_sort = [(Player.created_at, True)]


class Recap(BaseView):
    name = "Récapitulatif"
    icon = "fa-solid fa-table-list"

    @expose("/recap", methods=["GET"])
    async def recap(self, request: Request):
        names = {p.id: p.fr for p in REGULAR}
        served = func.sum(case((Play.redeemed_at.isnot(None), 1), else_=0))
        cost = func.sum(case((Play.redeemed_at.isnot(None), Play.value_cents), else_=0))
        with SessionLocal() as db:
            prize_rows = db.execute(select(Play.prize_id, func.count(), served, cost).group_by(Play.prize_id).order_by(func.count().desc())).all()
            day_rows = db.execute(select(Play.game_day, func.count(), served, cost, func.sum(case((Play.is_gold, 1), else_=0)))
                                  .group_by(Play.game_day).order_by(Play.game_day.desc())).all()
            players = db.scalar(select(func.count()).select_from(Player)) or 0
            consents = db.scalar(select(func.count()).select_from(Player).where(Player.marketing_consent.is_(True))) or 0
        euro = lambda c: f"{(c or 0) / 100:.2f} €".replace(".", ",")
        prizes = [{"name": "Lot en or du jour" if r[0] == "gold" else names.get(r[0], r[0]), "won": r[1], "served": r[2] or 0, "cost": euro(r[3])} for r in prize_rows]
        days = [{"day": r[0].strftime("%d/%m"), "won": r[1], "served": r[2] or 0, "cost": euro(r[3]), "gold": "oui" if r[4] else "non"} for r in day_rows]
        totals = {"plays": sum(r[1] for r in prize_rows), "served": sum(r[2] or 0 for r in prize_rows), "cost": euro(sum(r[3] or 0 for r in prize_rows)), "players": players, "consents": consents}
        return await self.templates.TemplateResponse(request, "noel_recap.html", {"prizes": prizes, "days": days, "totals": totals, "title": "Récapitulatif"})


def mount_admin(app) -> None:
    admin = Admin(app, engine, title="Roue de Noël", authentication_backend=Auth(secret_key=settings.app_secret), templates_dir=str(Path(__file__).parent / "templates"))
    admin.add_view(Recap)
    admin.add_view(PlayAdmin)
    admin.add_view(PlayerAdmin)
