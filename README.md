# Roue de Noël Miss Chawarma

- `frontend/index.html` : le jeu, à déposer dans `/www/noel/` sur Amen.
- `backend/` : API FastAPI + back-office SQLAdmin, service séparé du site.

## Mise en ligne

1. Créez un dépôt GitHub **privé** et poussez ce dossier. Le `.env` ne doit jamais y entrer.
2. Sur Neon, créez une base `noel` à part, et copiez son URL de connexion.
3. Sur Render : New > Blueprint > ce dépôt. Renseignez `DATABASE_URL`, `ADMIN_PASSWORD`, `STAFF_PIN` (6 chiffres), et les accès Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`) et Brevo (`BREVO_API_KEY`, `BREVO_SENDER_EMAIL`).
4. Vérifiez l'adresse du service. Si elle n'est pas `https://miss-chawarma-noel.onrender.com`, changez `api` en haut du script de `frontend/index.html`.
5. Déposez tout le contenu de `frontend/` dans `/www/noel/` sur Amen : `index.html`, `christmas-luxe.css`, `logo.png`, `logo-titre.png` et le dossier `assets/`.

## Tester avant le 1er décembre

Sur Render, mettez `GAME_START` à la date du jour, jouez, puis remettez `2026-12-01`. Videz ensuite la base dans la console SQL de Neon :

    TRUNCATE noel_plays, noel_gold_awards, noel_otp_challenges, noel_players RESTART IDENTITY;

Le SMS Twilio et l'email Brevo doivent marcher, sinon personne ne reçoit de code. `VERIFY_MODE=off` retire la vérification.

## Réglages

- Chances, lots et calendrier des lots en or : `backend/noel_app/prizes.py`.
- Back-office : `/admin` sur le service Render, menu Récapitulatif, Parties, Contacts.

## Après le jeu

Dans le Shell Render, avant de supprimer le service : `python -m noel_app.purge`. Supprime les joueurs sans accord pour les offres et les adresses IP.

## Tests

    pip install -r requirements.txt pytest
    TEST_DATABASE_URL=postgresql://... python -m pytest
