"""À lancer après le jeu : python -m noel_app.purge
Supprime les joueurs sans consentement et anonymise les parties pour garder les statistiques."""
from sqlalchemy import delete, select, update

from .db import SessionLocal
from .models import OtpChallenge, Play, Player


def main():
    with SessionLocal() as db:
        ids = list(db.scalars(select(Player.id).where(Player.marketing_consent.is_(False))))
        db.execute(update(Play).values(ip=None))
        if ids:
            db.execute(update(Play).where(Play.player_id.in_(ids)).values(player_id=None))
            db.execute(delete(Player).where(Player.id.in_(ids)))
        db.execute(delete(OtpChallenge))
        db.commit()
        print(f"{len(ids)} joueurs supprimés, adresses IP effacées.")


if __name__ == "__main__":
    main()
