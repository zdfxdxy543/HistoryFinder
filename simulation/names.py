"""Deterministic procedural names used by settlements and people."""

import random


# 英文风格音节（用于生成王国民、聚落名）
PREFIXES = [
    "Nor", "Ald", "Fal", "Thor", "Gar", "Bel", "Iron", "Riv", "Ash", "Storm",
    "Oak", "Dun", "Kal", "Mor", "Ver", "Ar", "El", "Cor", "Wyn", "Bran",
    "Silver", "Gold", "Red", "Black", "White", "High", "Deep", "North", "South",
    "East", "West", "Old", "New", "Kings", "Queens", "Grim", "Bright", "Dark",
]

SETTLEMENT_LINKS = [
    "en", "an", "in", "or", "ar", "el", "er", "al", "ing", "ow",
]

MIDDLES = [
    "en", "an", "in", "on", "ar", "el", "ir", "or", "al", "il",
    "wood", "field", "haven", "mark", "dale", "mere", "burg", "stone",
    "crest", "moor", "wych", "ford", "bridge", "gate", "shire",
]

SUFFIXES = [
    "ton", "ville", "burg", "heim", "stead", "reach", "hold", "keep",
    "watch", "fell", "rest", "vale", "peak", "fort", "wall", "fall",
    "cross", "well", "port", "mouth", "brook", "shire",
]

# 统治者名
RULER_PREFIXES = [
    "Ae", "Ala", "Bran", "Cae", "Dae", "Eri", "Fen", "Gwy", "Hael", "Ith",
    "Kael", "Lor", "Mae", "Nyl", "Ori", "Pyr", "Quin", "Rho", "Syl", "Thal",
    "Uri", "Vael", "Wyl", "Xan", "Yor", "Zeph",
]

RULER_SUFFIXES = [
    "dor", "mir", "rion", "thas", "wyn", "drin", "nor", "laith", "gar", "eth",
    "dred", "ric", "mund", "wald", "lin", "mar", "thon", "rak", "zar", "ven",
]


def generate_name(seed: int, style: str = "settlement") -> str:
    """
    根据种子生成名字。
    style: "settlement" | "ruler" | "kingdom" | "region"
    """
    rng = random.Random(seed)

    if style == "settlement":
        # Every settlement receives at least two components.  The former
        # one-word branch made collisions disproportionately common.
        pattern = rng.choice([
            "prefix_middle", "prefix_suffix", "linked_suffix",
            "middle_suffix",
        ])
        if pattern == "prefix_middle":
            return rng.choice(PREFIXES) + rng.choice(MIDDLES).lower()
        elif pattern == "prefix_suffix":
            return rng.choice(PREFIXES) + rng.choice(SUFFIXES).lower()
        elif pattern == "linked_suffix":
            return (rng.choice(PREFIXES) + rng.choice(SETTLEMENT_LINKS)
                    + rng.choice(SUFFIXES).lower())
        return rng.choice(MIDDLES).capitalize() + rng.choice(SUFFIXES).lower()

    elif style == "ruler":
        return rng.choice(RULER_PREFIXES) + rng.choice(RULER_SUFFIXES)

    elif style == "kingdom":
        prefix = rng.choice(["Kingdom of ", "Empire of ", "Dominion of ", "Realm of ", ""])
        if prefix:
            return prefix + generate_name(seed + 1000, "settlement")
        else:
            return generate_name(seed + 2000, "settlement") + "ia"

    elif style == "region":
        return rng.choice(PREFIXES) + rng.choice([" Marches", " Plains", " Valley",
                                                    " Mountains", " Coast", " Woods", " Moors"])

    return "Unknown"


def generate_unique_name(seed: int, used_names: set[str],
                         style: str = "settlement") -> str:
    """Derive and reserve a case-insensitively unique deterministic name."""
    normalized = {name.casefold() for name in used_names}
    attempt_limit = 1024
    if style == "ruler":
        name_space = len(RULER_PREFIXES) * len(RULER_SUFFIXES)
        if len(normalized) >= name_space:
            attempt_limit = 0
        elif len(normalized) >= name_space * 3 // 4:
            attempt_limit = 64

    for attempt in range(attempt_limit):
        # Collision retries are derived from the original draw, so they do not
        # consume the simulation's random stream and alter unrelated history.
        candidate_seed = seed + attempt * 1_000_003
        candidate = generate_name(candidate_seed, style)
        if candidate.casefold() not in normalized:
            used_names.add(candidate)
            return candidate

    # This is practically unreachable, but keeps uniqueness a guarantee even
    # if a future caller creates more settlements than the word space allows.
    root = generate_name(seed, style)
    sequence = len(normalized) + 2
    candidate = f"{root} {sequence}"
    while candidate.casefold() in normalized:
        sequence += 1
        candidate = f"{root} {sequence}"
    used_names.add(candidate)
    return candidate
