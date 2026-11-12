"""Lots et calendrier. C'est ici qu'on change les chances et les prix."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Prize:
    id: str
    fr: str
    en: str
    value_cents: int = 0
    weight: int = 0


REGULAR = [
    Prize("cafe", "Un café offert", "A free coffee", 250, 27),
    Prize("sandwich", "Un sandwich chawarma poulet offert", "A free chicken chawarma sandwich", 890, 3),
    Prize("tea", "Un Miss Tea offert", "A free Miss Tea", 200, 27),
    Prize("mouha", "Un mouhalabiyé offert", "A free mouhalabiyé", 490, 5),
    Prize("baklawa", "Un baklawa pistache offert", "A free pistachio baklawa", 250, 20),
    Prize("promo", "\u221210\u00a0% sur votre addition", "10% off your bill", 0, 5),
    Prize("lemon", "Une citronnade maison offerte", "A free homemade lemonade", 350, 13),
]
assert sum(p.weight for p in REGULAR) == 100

_TARBOUCH = ("Le menu Tarbouch offert", "A free Tarbouch combo", 1290)
_GOURMAND = ("Un café gourmand offert", "A free café gourmand", 790)
_MEZMIX = ("Le menu Mez'Mix offert", "A free Mez'Mix combo", 1390)
_BOWL = ("Le Mrs.bowl offert", "A free Mrs.bowl", 1190)
_MISS = ("Le menu Miss offert", "A free Miss combo", 1390)
_PLAT = ("Le plat chawarma poulet offert", "A free chicken chawarma plate", 1690)
_CYCLE = [_TARBOUCH, _GOURMAND, _MEZMIX, _BOWL, _MISS, _PLAT]

_SPECIALS = {
    12: ("Le menu Mez'Max offert", "A free Mez'Max combo", 1690),
    19: ("Le Mr. Tarbouch offert", "A free Mr. Tarbouch", 2000),
    24: ("Le Mezze Royal offert", "A free Mezze Royal", 2700),
    25: ("Le plat Miss Chawarma offert", "A free Miss Chawarma plate", 2300),
    31: ("Le Mezze Royal offert", "A free Mezze Royal", 2700),
}


def gold_for(day: date) -> Prize:
    fr, en, cents = _SPECIALS.get(day.day) or _CYCLE[(day.day - 1) % len(_CYCLE)]
    return Prize("gold", fr, en, cents)


def gold_probability(hour: int) -> float:
    """Le lot en or devient plus facile en fin de service pour être gagné presque chaque jour."""
    return 0.15 if hour >= 20 else 0.04


def regular_by_id(prize_id: str) -> Prize:
    return next(p for p in REGULAR if p.id == prize_id)
