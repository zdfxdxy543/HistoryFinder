import pytest

from simulation.effects import (
    DestroySettlement,
    EffectResolver,
    KillPerson,
    MarkRuinSurvivor,
    MovePerson,
    RelocatePopulation,
)
from simulation.events import HistoricalEvent
from simulation.mobility import (
    best_exchange_destination,
    plan_event_person_movements,
)
from simulation.person import Person
from simulation.text_carriers import materialize_text_carrier
from simulation.world import World
from game.local_map import LocalMapBuilder
from game.player_session import PlayerSession


def _world(years: int = 0) -> World:
    world = World(seed=42)
    world.generate(years=years)
    return world


def _local_informant(world, settlement_id: str, role: str):
    return next(
        (informant, world.persons[informant.person_id])
        for informant in world.informants.values()
        if informant.role == role
        and world.persons[informant.person_id].current_location_id
        == settlement_id
    )


def test_move_person_effect_preserves_home_and_reverses_travel_state():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    _, merchant = _local_informant(world, source.id, "merchant")
    history_before = list(merchant.movement_history)
    resolver = EffectResolver(seed=42)

    effect_ids = resolver.apply_effects([
        MovePerson(
            person_id=merchant.id,
            target_settlement_id=target.id,
            movement_type="trade_visit",
            event_id="event_trade_test",
            mobility_status="visitor",
            travel_role="merchant",
            stay_until_year=5,
            carried_evidence_ids=["evd_test"],
        )
    ], world)

    assert effect_ids
    assert merchant.settlement_id == source.id
    assert merchant.current_location_id == target.id
    assert merchant.travel_role == "merchant"
    assert merchant.carried_evidence_ids == ["evd_test"]
    assert merchant.movement_history[-1]["event_id"] == "event_trade_test"
    assert resolver.reverse_effect(effect_ids[0], world)
    assert merchant.current_location_id == source.id
    assert merchant.mobility_status == "resident"
    assert merchant.movement_history == history_before


def test_temporary_visitor_returns_home_after_the_planned_year():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    _, scholar = _local_informant(world, source.id, "scholar")
    assert world._effect_resolver.apply_effects([
        MovePerson(
            scholar.id, target.id, "scholarly_visit",
            mobility_status="visitor", travel_role="visiting_scholar",
            stay_until_year=2,
        )
    ], world)

    world.current_year = 3
    world._tick_person_mobility(3)

    assert scholar.current_location_id == source.id
    assert scholar.mobility_status == "resident"
    assert scholar.travel_role == ""
    assert scholar.movement_history[-1]["movement_type"] == "return_home"


def test_visitor_is_available_on_destination_map_and_player_payload():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    informant, merchant = _local_informant(world, source.id, "merchant")
    assert world._effect_resolver.apply_effects([
        MovePerson(
            merchant.id, target.id, "trade_visit",
            mobility_status="visitor", travel_role="merchant",
            stay_until_year=4,
        )
    ], world)

    assert informant not in world.get_available_informants(source.id)
    assert informant in world.get_available_informants(target.id)
    local_map = LocalMapBuilder().build(world, target)
    entity = next(item for item in local_map["entities"]
                  if item["id"] == informant.id)
    assert entity["state"] == "visitor"
    assert entity["zone"] == "外来者停留区"
    assert f"自称来自{source.name}" in entity["description_cn"]
    payload = PlayerSession(world, settlement_id=target.id).bootstrap()
    visitor = next(item for item in payload["informants"]
                   if item["id"] == informant.id)
    assert visitor["role_name"] == "商旅"
    assert visitor["claimed_origin_name"] == source.name
    assert visitor["origin_knowledge_status"] == "self_reported"
    assert f"自称来自{source.name}" in visitor["presence_label"]
    assert "origin_location_id" not in visitor
    assert "stay_until_year" not in visitor
    assert "mobility_status" not in visitor
    assert "travel_role" not in visitor


def test_hidden_travel_role_and_true_origin_are_not_exposed_to_player():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    informant, person = _local_informant(world, source.id, "merchant")
    assert world._effect_resolver.apply_effects([
        MovePerson(
            person.id, target.id, "covert_transfer",
            mobility_status="visitor", travel_role="smuggler",
            stay_until_year=4,
        )
    ], world)

    payload = PlayerSession(world, settlement_id=target.id).bootstrap()
    visitor = next(item for item in payload["informants"]
                   if item["id"] == informant.id)

    assert visitor["presence_label"] == "身份未明的外地人"
    assert visitor["claimed_origin_name"] == ""
    assert visitor["origin_knowledge_status"] == "unknown"
    assert source.id not in str(visitor)
    assert "smuggler" not in str(visitor)


def test_trade_events_link_merchants_to_the_objects_they_carried():
    world = _world(20)
    event = next(
        item for item in world.events
        if item.event_type == "trade"
        and item.details.get("person_movements")
        and item.details.get("object_transfers")
    )
    movement = event.details["person_movements"][0]
    transferred_ids = {
        item["evidence_id"] for item in event.details["object_transfers"]
        if item["transfer_type"] == "trade"
    }

    assert movement["travel_role"] == "merchant"
    assert set(movement["carried_evidence_ids"]) == transferred_ids
    assert movement["person_id"] in event.person_ids
    person = world.persons[movement["person_id"]]
    assert any(item["event_id"] == event.id
               for item in person.movement_history)
    ledger = next(
        item for item in world.evidence.values()
        if item.event_id == event.id and item.subtype == "trade_ledger"
    )
    materialize_text_carrier(world, ledger.id)
    text = "\n".join(
        item["text"]
        for item in ledger.content_data["written_content"]["passages"])
    record = world.records[ledger.source_record_id]
    assert movement["person_name"] in text
    assert any(claim.predicate == "person_moved"
               and claim.subject == movement["person_name"]
               for claim in record.claimed_facts)


def test_discovery_sends_a_scholar_and_spreads_the_exact_technology():
    world = _world()
    source = next(iter(world.settlements.values()))
    target = best_exchange_destination(
        world, source.id, "event_diffusion_discovery")
    before = target.technology_level
    event = HistoricalEvent(
        id="event_diffusion_discovery",
        year=1,
        event_type="discovery",
        title="Compound pulley completed",
        severity=0.25,
        primary_location=source.id,
        participants=[source.id],
        details={
            "technology_key": "compound_pulley",
            "discovery_name": "复合滑轮吊具",
            "artifact_subtype": "compound_pulley",
            "artifact_material": "wood",
            "description_cn": "工匠完成了一套可重复制作的滑轮组。",
        },
    )

    world._add_event_with_evidence(event)

    transfer = event.details["knowledge_transfers"][0]
    movement = event.details["person_movements"][0]
    assert transfer["dimension"] == "technology"
    assert transfer["topic_key"] == "compound_pulley"
    assert transfer["target_location_id"] == target.id
    assert target.technology_level == pytest.approx(
        before + transfer["delta"])
    assert movement["movement_type"] == "technology_demonstration"
    assert movement["to_location_id"] == target.id
    assert target.id in event.participants

    notes = next(
        item for item in world.evidence.values()
        if item.event_id == event.id and item.subtype == "research_notes")
    materialize_text_carrier(world, notes.id)
    text = "\n".join(
        passage["text"]
        for passage in notes.content_data["written_content"]["passages"])
    record = world.records[notes.source_record_id]
    assert transfer["person_name"] in text
    assert target.name in text
    assert transfer["topic_name"] in text
    assert any(claim.predicate == "knowledge_transferred"
               and claim.object == target.name
               for claim in record.claimed_facts)


def test_trade_carriage_can_diffuse_a_named_technology():
    world = _world(25)
    event = next(
        item for item in world.events
        if item.event_type == "trade"
        and any(transfer["dimension"] == "technology"
                for transfer in item.details.get(
                    "knowledge_transfers", [])))
    transfer = next(
        item for item in event.details["knowledge_transfers"]
        if item["dimension"] == "technology")

    assert transfer["source_evidence_id"]
    assert any(
        effect["effect_type"] == "modify_technology_level"
        and effect["settlement_id"] == transfer["target_location_id"]
        and effect["delta"] == transfer["delta"]
        for effect in event.effects)
    ledger = next(
        item for item in world.evidence.values()
        if item.event_id == event.id and item.subtype == "trade_ledger")
    materialize_text_carrier(world, ledger.id)
    text = "\n".join(
        passage["text"]
        for passage in ledger.content_data["written_content"]["passages"])
    assert transfer["topic_name"] in text
    assert transfer["person_name"] in text
    assert transfer["target_location_name"] in text


def test_theoretical_work_is_taught_in_another_settlement():
    world = _world()
    source = next(iter(world.settlements.values()))
    event = HistoricalEvent(
        id="event_theory_diffusion_test",
        year=2,
        event_type="theoretical_work",
        title="A mechanics treatise",
        severity=0.23,
        primary_location=source.id,
        participants=[source.id],
        details={
            "theory_field": "mechanics",
            "theory_field_name": "力学",
            "work_title": "重物、支点与绳索论",
            "author_name": "Test Scholar",
        },
    )
    world._add_event_with_evidence(event)
    transfer = event.details["knowledge_transfers"][0]
    movement = event.details["person_movements"][0]

    assert transfer["dimension"] == "theory"
    assert transfer["topic_key"] == event.details["theory_field"]
    assert transfer["source_event_id"] == event.id
    assert movement["movement_type"] == "scholarly_lecture"
    treatise = next(
        item for item in world.evidence.values()
        if item.event_id == event.id
        and item.subtype == "theoretical_treatise")
    materialize_text_carrier(world, treatise.id)
    text = "\n".join(
        passage["text"]
        for passage in treatise.content_data["written_content"]["passages"])
    assert transfer["person_name"] in text
    assert transfer["target_location_name"] in text


def test_war_victory_creates_a_persistent_captive_transfer():
    world = _world()
    attacker, defender = list(world.settlements.values())[:2]
    event = HistoricalEvent(
        id="event_captive_transfer_test",
        year=3,
        event_type="war",
        title="Test war",
        severity=0.7,
        primary_location=attacker.id,
        participants=[attacker.id, defender.id],
        details={"outcome": "attacker_victory"},
    )
    world._add_event_with_evidence(event)
    movement = next(
        item for item in event.details["person_movements"]
        if item["travel_role"] == "captive")
    captive = world.persons[movement["person_id"]]

    assert movement["stay_until_year"] is None
    assert captive.settlement_id == movement["from_location_id"]
    assert captive.current_location_id == movement["to_location_id"]
    assert captive.mobility_status == "captive"


def test_old_person_save_defaults_to_home_location():
    legacy = Person(
        id="person_legacy", name="Meren", birth_year=-30,
        settlement_id="stl_0001", roles=["scholar"],
    ).to_dict()
    for key in (
        "current_location_id", "mobility_status", "travel_role",
        "stay_until_year", "carried_evidence_ids", "movement_history",
    ):
        legacy.pop(key)
    legacy["schema_version"] = 1

    restored = Person.from_dict(legacy)

    assert restored.current_location_id == restored.settlement_id
    assert restored.mobility_status == "resident"
    assert restored.movement_history == []


def test_catastrophic_disaster_plans_refugees_to_a_living_settlement():
    world = _world()
    source = next(iter(world.settlements.values()))
    event = HistoricalEvent(
        id="event_disaster_test",
        year=4,
        event_type="disaster",
        title="test disaster",
        severity=1.0,
        primary_location=source.id,
        participants=[source.id],
        effects=[{
            "effect_type": "destroy_settlement",
            "settlement_id": source.id,
            "cause": "earthquake",
        }],
    )

    effects = plan_event_person_movements(world, event)

    assert effects
    refugees = [
        effect for effect in effects
        if isinstance(effect, MovePerson)
        and effect.travel_role == "refugee"
    ]
    assert refugees
    assert any(isinstance(effect, KillPerson) for effect in effects)
    assert any(isinstance(effect, MarkRuinSurvivor) for effect in effects)
    assert all(effect.stay_until_year is None for effect in refugees)
    assert all(effect.target_settlement_id != source.id for effect in refugees)


def test_disaster_person_and_population_effects_reverse_cleanly():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    _, merchant = _local_informant(world, source.id, "merchant")
    survivor = next(
        person for person in world.persons.values()
        if person.alive and person.current_location_id == source.id
        and person.id != merchant.id)
    source.alive = False
    source.population = 30
    populations_before = (source.population, target.population)
    resolver = EffectResolver(seed=42)

    effect_ids = resolver.apply_effects([
        KillPerson(merchant.id, "earthquake", death_year=4),
        MarkRuinSurvivor(survivor.id, source.id, year=4),
        RelocatePopulation(source.id, target.id, 20),
    ], world)

    assert effect_ids
    assert not merchant.alive and merchant.death_year == 4
    assert survivor.mobility_status == "ruin_survivor"
    assert (source.population, target.population) == (
        populations_before[0] - 20, populations_before[1] + 20)
    for effect_id in reversed(effect_ids):
        assert resolver.reverse_effect(effect_id, world)
    assert merchant.alive and merchant.death_year is None
    assert survivor.mobility_status == "resident"
    assert (source.population, target.population) == populations_before


def test_destroyed_settlement_survivors_are_distributed_and_visible():
    world = _world()
    ruin = next(iter(world.settlements.values()))
    ruin.population = 800
    ruin.peak_population = max(ruin.peak_population, ruin.population)
    world.current_year = 4
    disaster = HistoricalEvent(
        id="event_destroyed_population_test",
        year=4,
        event_type="disaster",
        title=f"{ruin.name}毁于地震",
        severity=0.95,
        primary_location=ruin.id,
        participants=[ruin.id],
    )
    destroy = DestroySettlement(ruin.id, cause="earthquake")
    disaster.effect_ids = world._effect_resolver.apply_effects(
        [destroy], world)
    disaster.effects = [{
        "effect_type": "destroy_settlement",
        "settlement_id": ruin.id,
        "cause": "earthquake",
    }]
    world._add_event_with_evidence(disaster)
    distribution = disaster.details["population_displacement"]

    assert not ruin.alive
    assert distribution["survivors_after_destruction"] > 0
    assert distribution["remaining_at_ruins"] == ruin.population
    assert sum(item["population"] for item in distribution["destinations"]) \
        + ruin.population == distribution["survivors_after_destruction"]
    living_people = [
        person for person in world.persons.values()
        if person.alive and person.settlement_id == ruin.id]
    assert all(
        person.current_location_id != ruin.id
        or person.mobility_status == "ruin_survivor"
        for person in living_people)

    session = PlayerSession(world, settlement_id=ruin.id)
    state = session.bootstrap()
    assert state["informants"]
    assert all(item["public_status"] == "survivor"
               for item in state["informants"])
    residents = [
        item for item in state["local_map"]["entities"]
        if item["kind"] == "resident"
    ]
    assert residents
    assert all(item["state"] == "ruin_survivor" for item in residents)
    conversation = session.talk(residents[0]["id"])
    assert conversation["dialogue_cn"]
