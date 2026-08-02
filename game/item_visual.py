"""Player-safe deterministic visual profiles for inspected evidence."""

from __future__ import annotations

import hashlib


VISUAL_PROFILE_VERSION = 1


def _visual_kind(evidence) -> str:
    subtype = evidence.subtype.removesuffix("_copy")
    if evidence.evidence_type == "document":
        if evidence.material == "stone" or "tablet" in subtype:
            return "tablet"
        if any(word in subtype for word in (
                "manuscript", "treatise", "liturgy", "journal")):
            return "codex"
        if any(word in subtype for word in (
                "charter", "decree", "contract", "edict")):
            return "scroll"
        return "sheet"
    if evidence.evidence_type == "structure":
        if any(word in subtype for word in (
                "marker", "pillar", "tomb", "temple", "stone")):
            return "monument"
        return "ruins"
    if evidence.evidence_type == "environmental":
        return "layer"
    if any(word in subtype for word in ("coin", "token")):
        return "coin"
    if "seal" in subtype:
        return "seal"
    if any(word in subtype for word in ("weapon", "sword", "blade")):
        return "weapon"
    if any(word in subtype for word in ("tool", "fitting")):
        return "tool"
    if any(word in subtype for word in ("jar", "crate", "vessel")):
        return "vessel"
    if any(word in subtype for word in ("icon", "relic")):
        return "icon"
    if any(word in subtype for word in ("model", "device", "mechanism")):
        return "model"
    return "fragment"


def _damage_features(evidence) -> list[str]:
    tags = set(evidence.physical_features.get("tags", []))
    damage = []
    rules = (
        ("water", {"mark:water_blurred_ink", "mark:round_stain"}),
        ("holes", {"mark:insect_holes"}),
        ("charred", {"surface:charred_side", "surface:flaking_surface"}),
        ("cracked", {"surface:jagged_break", "mark:impact_chips"}),
        ("rust", {"surface:pitted_corrosion", "surface:oxide_crust"}),
        ("torn", {"mark:missing_fold", "surface:frayed_fibers"}),
        ("soil", {"surface:soil_coating", "mark:soil_in_grooves"}),
        ("faded", {"surface:worn_smooth", "surface:dry_wrinkles"}),
    )
    for damage_type, matching_tags in rules:
        if tags & matching_tags:
            damage.append(damage_type)
    if evidence.state == "weathered" and "faded" not in damage:
        damage.append("faded")
    elif evidence.state == "ruined" and "cracked" not in damage:
        damage.append("cracked")
    elif evidence.state == "buried" and "soil" not in damage:
        damage.append("soil")
    return damage[:3]


def build_item_visual(evidence) -> dict:
    """Describe only observable properties needed by the pixel renderer."""
    digest = hashlib.sha256(
        f"{evidence.id}|item-visual-v{VISUAL_PROFILE_VERSION}".encode("utf-8")
    ).hexdigest()
    condition = (
        evidence.current_durability / evidence.max_durability
        if evidence.max_durability > 0 else 0.0
    )
    return {
        "version": VISUAL_PROFILE_VERSION,
        "seed": int(digest[:8], 16),
        "kind": _visual_kind(evidence),
        "material": evidence.material,
        "state": evidence.state,
        "condition": round(max(0.0, min(1.0, condition)), 3),
        "variant": int(digest[8:10], 16) % 4,
        "damage": _damage_features(evidence),
    }
