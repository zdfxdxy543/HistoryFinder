"""Literature, theory, and their downstream historical effects."""

import copy
import random

import pytest

from narrative.context_builder import build_evidence_context
from narrative.document_reader import read_document
from simulation.effects import (
    EffectResolver,
    ModifyCulturalInfluence,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
)
from simulation.event_rules import EventRuleRegistry
from simulation.events import HistoricalEvent
from simulation.pressures import tick_economy
from simulation.settlement import RelationshipData, Settlement
from simulation.world import World
from simulation.written_content import build_written_content


@pytest.fixture(scope="module")
def developed_world():
    world = World(seed=0)
    world.generate(years=100)
    return world


def test_knowledge_effects_apply_clamp_and_reverse():
    world = World(seed=200)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    resolver = EffectResolver(seed=200)

    effect_ids = resolver.apply_effects([
        ModifyCulturalInfluence(settlement.id, delta=20.0),
        ModifyTheoreticalKnowledge(settlement.id, delta=2.0),
        ModifyTechnologyLevel(settlement.id, delta=1.5),
    ], world)

    assert len(effect_ids) == 3
    assert settlement.cultural_influence == 10.0
    assert settlement.theoretical_knowledge == 2.0
    assert settlement.technology_level == 1.5

    for effect_id in reversed(effect_ids):
        assert resolver.reverse_effect(effect_id, world)
    assert settlement.cultural_influence == 0.0
    assert settlement.theoretical_knowledge == 0.0
    assert settlement.technology_level == 0.0


def test_technology_increases_food_production_with_identical_weather():
    baseline = Settlement(
        id="baseline", name="Baseline", grid_x=0, grid_y=0,
        founded_year=0, population=1000, biome="plains", food_stock=0.0,
    )
    advanced = copy.deepcopy(baseline)
    advanced.id = "advanced"
    advanced.technology_level = 5.0

    tick_economy(baseline, object(), random.Random(99))
    tick_economy(advanced, object(), random.Random(99))

    assert advanced.food_surplus > baseline.food_surplus
    assert advanced.food_shortage < baseline.food_shortage


def test_culture_improves_stability_recovery_with_identical_weather():
    baseline = Settlement(
        id="baseline", name="Baseline", grid_x=0, grid_y=0,
        founded_year=0, population=100, biome="river_valley",
        food_stock=500.0, stability=0.4,
    )
    influenced = copy.deepcopy(baseline)
    influenced.id = "influenced"
    influenced.cultural_influence = 5.0

    tick_economy(baseline, object(), random.Random(101))
    tick_economy(influenced, object(), random.Random(101))

    assert influenced.food_shortage == 0.0
    assert influenced.stability == pytest.approx(baseline.stability + 0.01)


def test_literary_and_theoretical_works_require_a_library():
    world = World(seed=201)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.population = 500
    settlement.treasury = 500.0
    registry = EventRuleRegistry()

    for event_type in ("literary_work", "theoretical_work"):
        condition = next(
            item for item in registry.rules[event_type].hard_conditions
            if item.name == "has_library"
        )
        settlement.infrastructure.pop("library", None)
        assert not condition.check(world, settlement, 1)
        settlement.infrastructure["library"] = 1.0
        assert condition.check(world, settlement, 1)


@pytest.mark.parametrize("genre", ["epic", "drama", "chronicle", "lyric_cycle"])
def test_literary_manuscripts_store_substantial_deterministic_text(genre):
    event = HistoricalEvent(
        id="event_literary", year=12, event_type="literary_work",
        title="A literary work", severity=0.2, primary_location="stl_1",
        details={
            "work_title": "The Returning Road",
            "author_name": "Eda",
            "genre": genre,
        },
    )

    first = build_written_content(event, "literary_manuscript", 42, "evd_1")
    second = build_written_content(event, "literary_manuscript", 42, "evd_1")
    stored_text = "".join(passage["text"] for passage in first["passages"])

    assert first == second
    assert len(first["passages"]) >= 15
    assert len(stored_text) >= 300


def test_theoretical_treatise_stores_method_limits_and_applications():
    event = HistoricalEvent(
        id="event_theory", year=20, event_type="theoretical_work",
        title="A theoretical work", severity=0.2, primary_location="stl_1",
        details={
            "work_title": "On Levers and Loads",
            "author_name": "Oren",
            "theory_field": "mechanics",
        },
    )

    written = build_written_content(
        event, "theoretical_treatise", 42, "evd_2")
    stored_text = "".join(passage["text"] for passage in written["passages"])

    assert len(written["passages"]) >= 17
    assert all(keyword in stored_text for keyword in (
        "试验布置", "反例", "适用限制", "可能用途", "复核办法",
    ))
    assert "尚需由工匠另行试制" in stored_text


def test_literary_spread_preserves_provenance_and_changes_target_culture():
    world = World(seed=202)
    world.generate(years=0)
    source, target = list(world.settlements.values())[:2]
    source.relationships[target.id] = RelationshipData(
        partner_id=target.id, trust=0.6, trade_volume=0.0)
    target.relationships[source.id] = RelationshipData(
        partner_id=source.id, trust=0.6, trade_volume=0.0)
    work = HistoricalEvent(
        id="event_literary_test", year=0, event_type="literary_work",
        title="Aren completes The Returning Road", severity=0.2,
        primary_location=source.id, participants=[source.id],
        process_id="literary_work:event_literary_test",
        details={
            "work_title": "The Returning Road",
            "author_name": "Aren",
            "genre": "epic",
            "genre_name": "长篇叙事诗",
        },
    )
    world.events.append(work)
    world._pending_literary_spreads.append((source.id, 0, work.id))
    culture_before = target.cultural_influence
    trust_before = source.relationships[target.id].trust

    world.current_year = 3
    world._process_literary_spreads(3)
    spread = world.events[-1]

    assert spread.event_type == "literary_spread"
    assert spread.cause_event_ids == [work.id]
    assert spread.process_id == work.process_id
    assert spread.details["genre"] == "epic"
    assert target.cultural_influence > culture_before
    assert source.relationships[target.id].trust > trust_before
    assert world._pending_literary_spreads == []


def test_pending_literary_spreads_roundtrip():
    world = World(seed=203)
    world.generate(years=0)
    source = next(iter(world.settlements.values()))
    world._pending_literary_spreads = [
        (source.id, 7, "event_literary_roundtrip")]

    restored = World.from_dict(world.to_dict())

    assert restored._pending_literary_spreads == [
        (source.id, 7, "event_literary_roundtrip")]


def test_theory_can_be_a_direct_cause_of_later_technology(developed_world):
    events_by_id = {event.id: event for event in developed_world.events}
    linked_discoveries = [
        event for event in developed_world.events
        if event.event_type == "discovery"
        and any(events_by_id[cause_id].event_type == "theoretical_work"
                for cause_id in event.cause_event_ids)
    ]

    assert linked_discoveries
    for discovery in linked_discoveries:
        assert any(
            events_by_id[cause_id].year < discovery.year
            for cause_id in discovery.cause_event_ids
            if events_by_id[cause_id].event_type == "theoretical_work"
        )


def test_new_documents_keep_source_truth_out_of_examination_context(
        developed_world):
    for event_type, subtype in (
            ("literary_work", "literary_manuscript"),
            ("theoretical_work", "theoretical_treatise")):
        evidence = next(
            item for item in developed_world.evidence.values()
            if item.subtype == subtype and item.state != "destroyed"
        )
        source_event = developed_world.get_event(evidence.event_id)
        context = build_evidence_context(evidence)
        reading = read_document(evidence, {"common"})

        assert source_event.event_type == event_type
        assert "event_id" not in context
        assert "event_details" not in context
        assert "这件证物与" not in reading["text"]
        assert reading["visible_passages"]
