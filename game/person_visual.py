"""Deterministic, player-safe visual profiles for NPC pixel portraits."""

from __future__ import annotations

import hashlib


PERSON_VISUAL_VERSION = 1

_ROLE_STYLES = {
    "scholar": ("scholar", "cap"),
    "scribe": ("scholar", "cap"),
    "elder": ("common", "wrap"),
    "merchant": ("merchant", "cap"),
    "artisan": ("artisan", "none"),
    "guard": ("guard", "helmet"),
    "road_guard": ("guard", "helmet"),
    "sentry": ("guard", "helmet"),
    "watch_captain": ("guard", "helmet"),
    "soldier": ("guard", "helmet"),
    "farmer": ("laborer", "hat"),
    "farmhand": ("laborer", "hat"),
    "miner": ("laborer", "hood"),
    "mine_foreman": ("laborer", "hood"),
    "woodcutter": ("laborer", "cap"),
    "logging_foreman": ("laborer", "cap"),
    "innkeeper": ("merchant", "none"),
    "hostler": ("laborer", "cap"),
    "toll_keeper": ("official", "cap"),
    "groundskeeper": ("common", "hood"),
    "priest": ("cleric", "hood"),
    "survivor": ("traveler", "hood"),
}


def _stable_bytes(person_id: str, role: str) -> bytes:
    return hashlib.sha256(
        f"{person_id}|{role}|person-visual-v{PERSON_VISUAL_VERSION}"
        .encode("utf-8")
    ).digest()


def _age_group(age: int | None, value: int) -> str:
    if age is None:
        return ("young", "adult", "adult", "mature", "elder")[value % 5]
    if age < 24:
        return "young"
    if age < 45:
        return "adult"
    if age < 65:
        return "mature"
    return "elder"


def build_person_visual(person_id: str, role: str, *,
                        state: str = "", age: int | None = None) -> dict:
    """Describe visible portrait traits without exposing hidden simulation data."""
    digest = _stable_bytes(person_id, role)
    outfit, default_headwear = _ROLE_STYLES.get(role, ("common", "none"))
    headwear = default_headwear
    if headwear == "none" and digest[6] % 5 == 0:
        headwear = ("cap", "wrap", "hood")[digest[7] % 3]
    age_group = _age_group(age, digest[8])
    hair_style = ("short", "cropped", "long", "braided", "wavy")[digest[5] % 5]
    if age_group == "elder" and digest[9] % 3 == 0:
        hair_style = "balding"
    expression = ("calm", "warm", "focused", "stern")[digest[10] % 4]
    if state in {"survivor", "ruin_survivor", "captive", "damaged"}:
        expression = "weary"
    detail = ("none", "freckles", "scar", "earring")[digest[11] % 4]
    return {
        "version": PERSON_VISUAL_VERSION,
        "seed": int.from_bytes(digest[:4], "big"),
        "skin_tone": digest[4] % 6,
        "hair_color": digest[3] % 6,
        "hair_style": hair_style,
        "face_shape": ("round", "oval", "angular")[digest[2] % 3],
        "age_group": age_group,
        "outfit": outfit,
        "headwear": headwear,
        "expression": expression,
        "detail": detail,
        "accent": digest[1] % 6,
    }
