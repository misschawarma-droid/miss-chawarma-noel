from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import game
from .admin import mount_admin
from .config import settings
from .db import Base, engine, get_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Roue de Noël Miss Chawarma", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Noel-Token"], expose_headers=["X-Noel-Token"], allow_credentials=False)
mount_admin(app)


class CodeRequest(BaseModel):
    contact: str = Field(max_length=254)
    lang: str = Field(default="fr", pattern="^(fr|en)$")


class PlayRequest(BaseModel):
    contact: str | None = Field(default=None, max_length=254)
    otp: str | None = Field(default=None, max_length=6)
    accept_rules: bool = False
    marketing: bool = False
    lang: str = Field(default="fr", pattern="^(fr|en)$")


class RedeemRequest(BaseModel):
    code: str = Field(max_length=16)
    pin: str = Field(max_length=6)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/state")
def get_state(db: Session = Depends(get_db), x_noel_token: str | None = Header(default=None)):
    return game.state(db, x_noel_token)


@app.post("/api/request-code")
def request_code(body: CodeRequest, request: Request, db: Session = Depends(get_db)):
    return game.request_code(db, body.contact, body.lang, game.client_ip(request))


@app.post("/api/play")
def play(body: PlayRequest, request: Request, db: Session = Depends(get_db), x_noel_token: str | None = Header(default=None)):
    return game.play(db, x_noel_token, body.contact, body.otp, body.accept_rules, body.marketing, body.lang, game.client_ip(request))


@app.post("/api/redeem")
def redeem(body: RedeemRequest, db: Session = Depends(get_db)):
    return game.redeem(db, body.code, body.pin)
