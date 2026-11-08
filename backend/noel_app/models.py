from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Player(Base):
    __tablename__ = "noel_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Empreinte du contact : sert à limiter le jeu sans garder le numéro en clair.
    contact_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    contact_type: Mapped[str] = mapped_column(String(8))
    # Renseigné seulement si la personne a coché la case d'offres.
    contact: Mapped[str | None] = mapped_column(String(254), nullable=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lang: Mapped[str] = mapped_column(String(2), default="fr")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    plays: Mapped[list["Play"]] = relationship(back_populates="player")

    def __str__(self) -> str:
        return f"Joueur {self.id}"


class Play(Base):
    __tablename__ = "noel_plays"
    __table_args__ = (
        UniqueConstraint("player_id", "game_day", name="uq_noel_player_day"),
        Index("ix_noel_plays_day_ip", "game_day", "ip"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("noel_players.id"), nullable=True, index=True)
    game_day: Mapped[date] = mapped_column(Date, index=True)
    prize_id: Mapped[str] = mapped_column(String(16))
    label_fr: Mapped[str] = mapped_column(String(80))
    label_en: Mapped[str] = mapped_column(String(80))
    value_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_gold: Mapped[bool] = mapped_column(Boolean, default=False)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pin_failures: Mapped[int] = mapped_column(Integer, default=0)

    player: Mapped[Player | None] = relationship(back_populates="plays")

    def __str__(self) -> str:
        return self.code


class GoldAward(Base):
    """Une seule ligne par jour : la clé primaire garantit un seul lot en or."""
    __tablename__ = "noel_gold_awards"

    game_day: Mapped[date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OtpChallenge(Base):
    __tablename__ = "noel_otp_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
