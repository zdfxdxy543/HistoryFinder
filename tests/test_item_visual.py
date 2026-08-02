"""Deterministic player-safe evidence visual profile tests."""

from types import SimpleNamespace

import pytest

from game.item_visual import build_item_visual


def _evidence(subtype: str, evidence_type: str = "artifact",
              material: str = "metal", tags=(), state: str = "intact"):
    return SimpleNamespace(
        id=f"evidence_{subtype}",
        subtype=subtype,
        evidence_type=evidence_type,
        material=material,
        state=state,
        current_durability=75.0,
        max_durability=100.0,
        physical_features={"tags": list(tags)},
    )


@pytest.mark.parametrize(("subtype", "evidence_type", "material", "kind"), (
    ("literary_manuscript", "document", "parchment", "codex"),
    ("founding_charter", "document", "parchment", "scroll"),
    ("treaty_tablet", "document", "stone", "tablet"),
    ("trade_ledger", "document", "parchment", "sheet"),
    ("foreign_coin", "artifact", "metal", "coin"),
    ("official_seal", "artifact", "metal", "seal"),
    ("duel_weapon", "artifact", "metal", "weapon"),
    ("builders_tools", "artifact", "metal", "tool"),
    ("grain_storage_jar", "artifact", "stone", "vessel"),
    ("damaged_icon", "artifact", "stone", "icon"),
    ("demonstration_model", "artifact", "wood", "model"),
    ("damaged_relics", "artifact", "metal", "icon"),
    ("crafted_item", "artifact", "metal", "fragment"),
    ("grave_marker", "structure", "stone", "monument"),
    ("battlefield_ruins", "structure", "stone", "ruins"),
    ("burn_layer", "environmental", "stone", "layer"),
))
def test_visual_profile_selects_observable_shape(
        subtype, evidence_type, material, kind):
    profile = build_item_visual(_evidence(
        subtype, evidence_type=evidence_type, material=material))

    assert profile["kind"] == kind
    assert profile["material"] == material
    assert set(profile) == {
        "version", "seed", "kind", "material", "state", "condition",
        "variant", "damage",
    }


def test_visual_profile_is_deterministic_and_uses_physical_damage_only():
    evidence = _evidence(
        "trade_ledger", evidence_type="document", material="parchment",
        tags=("mark:water_blurred_ink", "mark:insect_holes"),
        state="weathered",
    )

    first = build_item_visual(evidence)
    second = build_item_visual(evidence)

    assert first == second
    assert first["damage"] == ["water", "holes", "faded"]
    assert first["condition"] == 0.75
