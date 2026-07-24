"""Religion state, evidence, informants, and map projection tests."""

import hashlib

from game.local_map import LocalMapBuilder
from game.local_time import WORKPLACE_TYPES
from game.world_cell_map import WorldCellMapBuilder
from simulation.effects import (
    EffectResolver,
    ModifyReligiousPresence,
    ModifyReligiousTolerance,
)
from simulation.informants import INFORMANT_ROLES
from simulation.religion import (
    ReligionTradition,
    changed_profile_dimensions,
)
from simulation.world import World


def test_initial_religions_are_deterministic_and_have_priest_informants():
    first = World(seed=461)
    first.generate(years=0)
    second = World(seed=461)
    second.generate(years=0)

    assert {
        key: value.to_dict() for key, value in first.religions.items()
    } == {
        key: value.to_dict() for key, value in second.religions.items()
    }
    assert len(first.religions) == len(first.settlements)
    for settlement in first.settlements.values():
        religion = first.religions[settlement.official_religion_id]
        assert settlement.religious_presence == {religion.id: 1.0}
        assert religion.origin_settlement_id == settlement.id
        assert religion.doctrine
        assert religion.sacred_symbol
        assert religion.primary_ritual
        assert religion.taboo
        roles = {
            item.role for item in first.get_available_informants(settlement.id)}
        assert roles == set(INFORMANT_ROLES)
        assert "priest" in roles


def test_religion_world_roundtrip_preserves_plural_state():
    world = World(seed=462)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    original = world.religions[settlement.official_religion_id]
    reformed = world._religion_mgr.create_reform(
        original, settlement, 1, "祭历日期长期不一致")
    settlement.religious_presence[reformed.id] = 0.35
    settlement.religious_tolerance = 0.81

    restored = World.from_dict(world.to_dict())

    assert {
        key: item.to_dict() for key, item in restored.religions.items()
    } == {
        key: item.to_dict() for key, item in world.religions.items()
    }
    restored_settlement = restored.settlements[settlement.id]
    assert restored_settlement.religious_presence == \
        settlement.religious_presence
    assert restored_settlement.official_religion_id == original.id
    assert restored_settlement.religious_tolerance == 0.81


def test_religious_effects_are_clamped_and_reversible():
    world = World(seed=463)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    religion = next(iter(world.religions.values()))
    resolver = EffectResolver(seed=463)

    effect_ids = resolver.apply_effects([
        ModifyReligiousPresence(
            settlement.id, religion.id, -0.4, "test"),
        ModifyReligiousTolerance(settlement.id, -2.0, "test"),
    ], world)

    assert len(effect_ids) == 2
    assert settlement.religious_presence[religion.id] == 0.6
    assert settlement.religious_tolerance == 0.0
    assert resolver.reverse_effect(effect_ids[1], world)
    assert resolver.reverse_effect(effect_ids[0], world)
    assert settlement.religious_presence[religion.id] == 1.0
    assert settlement.religious_tolerance == 0.72


def test_temple_construction_materializes_religious_evidence_and_fixtures():
    world = World(seed=464)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.size = "city"
    settlement.population = 2200
    settlement.peak_population = 2200
    settlement.infrastructure["temple"] = 1.0
    event = world._event_gen.generate_construction_event(
        1, settlement.id, settlement.name, "temple")

    world._add_event_with_evidence(event)

    subtypes = {
        item.subtype.removesuffix("_copy")
        for item in world.get_evidence_by_event(event.id)}
    assert {"temple", "religious_text", "hymn"} <= subtypes
    religious_text = next(
        item for item in world.get_evidence_by_event(event.id)
        if item.subtype == "religious_text")
    assert world.storage_sites[
        religious_text.container_id].site_type == "temple_repository"
    assert event.details["religion_id"] == settlement.official_religion_id

    local_map = LocalMapBuilder().build(world, settlement)
    fixtures = {
        item["subtype"] for item in local_map["entities"]
        if item["kind"] == "landmark"
    }
    assert {"temple_altar", "offering_table", "votive_wall"} <= fixtures


def test_reform_and_conflict_leave_distinct_sources_known_to_priest():
    world = World(seed=465)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    parent = world.religions[settlement.official_religion_id]
    reformed = world._religion_mgr.create_reform(
        parent, settlement, 5, "旧抄本之间的措辞差异")
    settlement.religious_presence[reformed.id] = 0.32
    priest = next(
        item for item in world.get_available_informants(settlement.id)
        if item.role == "priest")
    person = world.persons[priest.person_id]

    reform = world._event_gen.generate_religious_reform_event(
        5, settlement.id, settlement.name, parent, reformed,
        person.id, person.name)
    conflict = world._event_gen.generate_religious_conflict_event(
        8, settlement.id, settlement.name, parent, reformed)
    world._add_event_with_evidence(reform)
    world._add_event_with_evidence(conflict)

    reform_subtypes = {
        item.subtype.removesuffix("_copy")
        for item in world.get_evidence_by_event(reform.id)}
    conflict_subtypes = {
        item.subtype.removesuffix("_copy")
        for item in world.get_evidence_by_event(conflict.id)}
    assert reform_subtypes == {
        "reformed_liturgy", "reform_decree", "revised_hymn"}
    assert conflict_subtypes == {
        "prohibition_edict", "damaged_icon", "forbidden_hymn"}
    known_subtypes = {
        world.evidence[world.knowledge_entries[entry_id].source_evidence_id]
        .subtype.removesuffix("_copy")
        for entry_id in priest.known_entry_ids
    }
    assert {"reformed_liturgy", "reform_decree", "revised_hymn",
            "prohibition_edict", "forbidden_hymn"} <= known_subtypes


def test_wilderness_sacred_site_is_deterministic_and_observable():
    world = World(seed=466)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    religion = world.religions[settlement.official_religion_id]
    chosen = None
    for y in range(max(0, settlement.grid_y - 10),
                   min(world.geography.height, settlement.grid_y + 11)):
        for x in range(max(0, settlement.grid_x - 10),
                       min(world.geography.width, settlement.grid_x + 11)):
            if str(world.geography.biomes[y, x]) in {"ocean", "lake"}:
                continue
            if abs(settlement.grid_x - x) + abs(settlement.grid_y - y) > 10:
                continue
            value = int.from_bytes(hashlib.sha256(
                f"{world.seed}|{x}|{y}|sacred-shrine".encode("utf-8")
            ).digest()[:8], "big")
            if value % 17 == 0:
                chosen = (x, y)
                break
        if chosen:
            break

    assert chosen is not None
    first = WorldCellMapBuilder().build(world, *chosen)
    second = WorldCellMapBuilder().build(world, *chosen)
    shrine = next(
        item for item in first["entities"]
        if item["subtype"] == "sacred_shrine")
    assert shrine in second["entities"]
    assert shrine["role_name"] == "荒野圣所"
    assert religion.name in shrine["description_cn"]
    assert shrine["blocks_movement"] is False


def test_priest_has_no_temple_specific_schedule():
    assert "priest" not in WORKPLACE_TYPES


def test_religion_tradition_roundtrip():
    tradition = ReligionTradition(
        id="religion_0001", name="守火之誓", founded_year=4,
        origin_settlement_id="stl_0001", parent_id=None,
        doctrine="共同守誓", sacred_symbol="三道火焰纹",
        primary_ritual="黄昏守灯", taboo="不得污染公共水源",
        sacred_landscape="open_sky",
    )
    assert ReligionTradition.from_dict(tradition.to_dict()) == tradition


def test_generated_religions_have_composable_text_profiles():
    world = World(seed=468)
    world.generate(years=0)
    profiles = [item.text_profile() for item in world.religions.values()]

    assert all(len(profile["ritual_steps"]) >= 4 for profile in profiles)
    assert len({profile["sacred_focus"] for profile in profiles}) >= 3
    assert len({profile["offering"] for profile in profiles}) >= 3
    assert len({profile["congregation_response"] for profile in profiles}) >= 3


def test_reform_always_changes_a_serialized_semantic_dimension():
    world = World(seed=469)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    parent = world.religions[settlement.official_religion_id]
    reformed = world._religion_mgr.create_reform(
        parent, settlement, 3, "供物与答词的抄本不一致")
    changed = changed_profile_dimensions(
        parent.text_profile(), reformed.text_profile())

    assert changed
    restored = ReligionTradition.from_dict(reformed.to_dict())
    assert restored.ritual_steps == reformed.ritual_steps
    assert changed_profile_dimensions(
        parent.text_profile(), restored.text_profile()) == changed
