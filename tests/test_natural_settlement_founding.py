"""Dynamic site planning and planned-colony integration tests."""

import json

from config import (
    DYNAMIC_FOUNDING_MAX_SETTLERS,
    DYNAMIC_FOUNDING_MIN_SETTLERS,
    DYNAMIC_FOUNDING_MIN_SOURCE_POPULATION,
    DYNAMIC_FOUNDING_MIN_SUITABILITY,
    DYNAMIC_FOUNDING_MAX_WORLD_SETTLEMENTS,
)
from simulation.effects import FoundSettlement, effect_to_dict
from simulation.founding import (
    BLOCKED_FOUNDING_BIOMES,
    SettlementFoundingPlanner,
    find_founding_sites,
)
from simulation.informants import INFORMANT_ROLES
from simulation.pressures import compute_all_pressures
from simulation.world import World


class AlwaysFoundPlanner(SettlementFoundingPlanner):
    @staticmethod
    def _roll(world, source, year: int) -> float:
        return 0.0


class NeverFoundPlanner(SettlementFoundingPlanner):
    @staticmethod
    def _roll(world, source, year: int) -> float:
        return 1.0


def _ready_world(seed=42, year=20):
    world = World(seed=seed)
    world.generate(years=0)
    world.current_year = year
    source = next(iter(world.settlements.values()))
    source.population = 1200
    source.peak_population = 1200
    source.food_stock = 10000.0
    source.food_shortage = 0.0
    source.treasury = 1000.0
    source.stability = 0.90
    source.legitimacy = 0.90
    world._pressures_cache = compute_all_pressures(world)
    return world, source


def _plan(world, source):
    plan = AlwaysFoundPlanner().evaluate(
        world, source, world.current_year)
    assert plan is not None
    return plan


def _effect_for(world, plan):
    source = world.settlements[plan.source_settlement_id]
    founder = world.persons[plan.founder_person_id]
    return FoundSettlement(
        source_settlement_id=source.id,
        new_settlement_id=world._settlement_mgr.reserve_id(),
        new_settlement_name=world._settlement_mgr.reserve_name(),
        grid_x=plan.x,
        grid_y=plan.y,
        founded_year=world.current_year,
        biome=plan.biome,
        settler_count=plan.settler_count,
        food_transfer=plan.food_transfer,
        treasury_transfer=plan.treasury_transfer,
        founder_person_id=founder.id,
        controller_polity_id=plan.controller_polity_id,
        control_period_id=world._polity_mgr.reserve_control_id(),
        event_id=world._event_gen.reserve_id(),
    )


def test_dynamic_site_search_is_legal_and_deterministic():
    world, source = _ready_world()

    first = find_founding_sites(world, source)
    second = find_founding_sites(world, source)

    assert first
    assert first == second
    occupied = {
        (item.grid_x, item.grid_y) for item in world.settlements.values()}
    for site in first:
        assert 0 <= site.x < world.geography.width
        assert 0 <= site.y < world.geography.height
        assert site.biome not in BLOCKED_FOUNDING_BIOMES
        assert (site.x, site.y) not in occupied
        assert site.suitability >= DYNAMIC_FOUNDING_MIN_SUITABILITY
        assert site.nearest_settlement_distance >= 10


def test_planner_is_pure_deterministic_and_resources_are_bounded():
    world, source = _ready_world()
    snapshot = json.dumps(world.to_dict(), sort_keys=True, ensure_ascii=False)

    first = _plan(world, source)
    second = _plan(world, source)

    assert first == second
    assert json.dumps(world.to_dict(), sort_keys=True, ensure_ascii=False) \
        == snapshot
    assert DYNAMIC_FOUNDING_MIN_SETTLERS \
        <= first.settler_count <= DYNAMIC_FOUNDING_MAX_SETTLERS
    assert first.food_transfer <= source.food_stock
    assert first.treasury_transfer <= 120.0
    assert first.controller_polity_id == source.controller_polity_id
    assert world.persons[first.founder_person_id].id != source.ruler_id


def test_planner_rejects_hard_conditions_and_protection():
    world, source = _ready_world()
    planner = AlwaysFoundPlanner()

    source.population = DYNAMIC_FOUNDING_MIN_SOURCE_POPULATION - 1
    assert planner.evaluate(world, source, world.current_year) is None
    source.population = 1200
    source.protected_until_year = world.current_year
    assert planner.evaluate(world, source, world.current_year) is None
    source.protected_until_year = 0
    source.food_shortage = 0.2
    assert planner.evaluate(world, source, world.current_year) is None


def test_planner_skips_site_scan_when_probability_roll_cannot_succeed(
        monkeypatch):
    world, source = _ready_world()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("site scan should have been skipped")

    monkeypatch.setattr(
        "simulation.founding.find_founding_sites", fail_if_called)
    assert NeverFoundPlanner().evaluate(
        world, source, world.current_year) is None


def test_planner_rejects_world_at_settlement_cap(monkeypatch):
    world, source = _ready_world()
    monkeypatch.setattr(
        "simulation.founding.DYNAMIC_FOUNDING_MAX_WORLD_SETTLEMENTS",
        len(world.settlements),
    )

    assert AlwaysFoundPlanner().evaluate(
        world, source, world.current_year) is None
    assert DYNAMIC_FOUNDING_MAX_WORLD_SETTLEMENTS == 100


def test_found_settlement_effect_is_conservative_and_reversible():
    world, source = _ready_world()
    plan = _plan(world, source)
    effect = _effect_for(world, plan)
    founder = world.persons[effect.founder_person_id]
    founder_before = founder.to_dict()
    population_before = sum(item.population for item in world.settlements.values())
    food_before = source.food_stock
    treasury_before = source.treasury

    effect_ids = world._effect_resolver.apply_effects([effect], world)

    assert effect_ids
    settlement = world.settlements[effect.new_settlement_id]
    assert sum(item.population for item in world.settlements.values()) \
        == population_before
    assert source.food_stock + settlement.food_stock == food_before
    assert source.treasury + settlement.treasury == treasury_before
    assert settlement.origin_settlement_id == source.id
    assert settlement.controller_polity_id == source.controller_polity_id
    assert settlement.ruler_id == founder.id
    assert founder.settlement_id == settlement.id
    assert {"colonist_leader", "founder", "ruler"} <= set(founder.roles)
    assert "heir" not in founder.roles
    assert world.get_current_control_period(settlement.id).event_id \
        == effect.event_id
    assert effect_to_dict(effect)["effect_type"] == "found_settlement"

    assert world._effect_resolver.reverse_effect(effect_ids[0], world)
    assert effect.new_settlement_id not in world.settlements
    assert effect.control_period_id not in world.settlement_control_periods
    assert source.population == population_before - sum(
        item.population for item in world.settlements.values()
        if item.id != source.id)
    assert source.food_stock == food_before
    assert source.treasury == treasury_before
    assert founder.to_dict() == founder_before


def test_execute_plan_creates_history_people_evidence_and_roundtrips():
    world, source = _ready_world()
    plan = _plan(world, source)
    founder_was_heir = "heir" in world.persons[plan.founder_person_id].roles

    event = world._execute_founding_plan(plan, world.current_year)

    assert event is not None
    settlement = world.settlements[event.primary_location]
    assert event.event_type == "founding"
    assert event.participants == [settlement.id, source.id]
    assert event.id in world.event_history_by_settlement[settlement.id]
    assert event.id in world.event_history_by_settlement[source.id]
    assert event.details["origin_settlement_id"] == source.id
    assert event.details["settler_count"] == plan.settler_count
    assert event.details["founding_type"] == "planned_colony"
    assert event.effects[0]["effect_type"] == "found_settlement"
    assert event.person_ids == [plan.founder_person_id]
    assert settlement.protected_until_year == world.current_year + 3
    assert {item.role for item in world.get_available_informants(
        settlement.id)} == set(INFORMANT_ROLES)
    assert any(
        person.alive and person.settlement_id == settlement.id
        and "heir" in person.roles
        for person in world.persons.values())
    if founder_was_heir:
        assert any(
            person.alive and person.settlement_id == source.id
            and "heir" in person.roles
            for person in world.persons.values())
    subtypes = {
        evidence.subtype for evidence in world.evidence.values()
        if evidence.event_id == event.id
    }
    assert {"founding_charter", "foundation_stone", "founding_legend"} \
        <= subtypes
    charter = next(
        evidence for evidence in world.evidence.values()
        if evidence.event_id == event.id
        and evidence.subtype == "founding_charter")
    written = charter.content_data.get("written_content")
    if written:
        text = "\n".join(item["text"] for item in written["passages"])
        assert source.name in text

    restored = World.from_dict(json.loads(json.dumps(world.to_dict())))
    restored_settlement = restored.settlements[settlement.id]
    assert restored_settlement.origin_settlement_id == source.id
    assert restored_settlement.controller_polity_id \
        == source.controller_polity_id
    restored._validate_political_state()


def test_yearly_founding_respects_global_limit():
    world, source = _ready_world()
    second = list(world.settlements.values())[1]
    second.population = source.population
    second.peak_population = source.peak_population
    second.food_stock = source.food_stock
    second.food_shortage = 0.0
    second.treasury = source.treasury
    second.stability = source.stability
    second.legitimacy = source.legitimacy
    world._pressures_cache = compute_all_pressures(world)
    world._founding_planner = AlwaysFoundPlanner()
    before = len(world.settlements)

    event_ids = world._evaluate_natural_founding(world.current_year)

    assert len(event_ids) <= 1
    assert len(world.settlements) == before + len(event_ids)
