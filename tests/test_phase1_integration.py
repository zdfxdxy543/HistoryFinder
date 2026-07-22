"""Phase 1 行为级验收测试。"""

from collections import defaultdict

from simulation.settlement import RelationshipData
from simulation.world import World


RULE_EVENT_TYPES = {
    "economic", "disaster", "construction", "rebellion",
    "war", "trade", "literary_work", "theoretical_work", "discovery",
    "literary_spread", "reconstruction", "relief", "decline",
}


def _queue_test_disaster(world, settlement, disaster_type="flood"):
    event = world._event_gen.generate_disaster_event(
        1, settlement.id, settlement.name, disaster_type)
    event.effects = [{"effect_type": "modify_stability", "delta": -0.1}]
    event.effect_ids = ["setup_effect"]
    event.process_id = f"disaster_aftermath:{event.id}"
    world._add_event_with_evidence(event)
    world._pending_disaster_aftermaths.append(
        (settlement.id, 1, event.id, disaster_type))
    return event


def test_rule_events_apply_and_persist_effects():
    world = World(seed=42)
    world.generate(years=40)

    events = [e for e in world.events if e.event_type in RULE_EVENT_TYPES]
    assert events
    assert all(e.effect_ids for e in events)
    assert all(e.effects for e in events)


def test_two_party_events_use_one_consistent_target():
    world = World(seed=42)
    world.generate(years=60)

    events = [
        e for e in world.events
        if e.event_type in {"war", "trade", "relief"}
        and len(e.participants) == 2
    ]
    assert events
    for event in events:
        participant_names = [world.settlements[pid].name for pid in event.participants]
        assert all(name in event.title for name in participant_names)


def test_food_economy_does_not_force_every_settlement_to_zero_stock():
    world = World(seed=42)
    world.generate(years=100)

    alive = [s for s in world.settlements.values() if s.alive]
    assert alive
    assert any(s.food_stock > 0 for s in alive)
    assert all(s.food_stock >= 0 and 0.0 <= s.food_shortage <= 1.0 for s in alive)


def test_causal_edges_are_prior_state_changing_events():
    world = World(seed=42)
    world.generate(years=100)
    event_by_id = {event.id: event for event in world.events}

    caused = [event for event in world.events if event.cause_event_ids]
    assert caused
    for event in caused:
        for cause_id in event.cause_event_ids:
            cause = event_by_id[cause_id]
            assert cause.year < event.year
            assert cause.effects

    assert all(not event.cause_event_ids
               for event in world.events if event.event_type == "disaster")


def test_war_cooldown_is_enforced_per_pair():
    world = World(seed=42)
    world.generate(years=100)
    years_by_pair = defaultdict(list)

    for event in world.events:
        if event.event_type == "war" and len(event.participants) == 2:
            years_by_pair[tuple(sorted(event.participants))].append(event.year)

    for years in years_by_pair.values():
        assert all(later - earlier >= 8
                   for earlier, later in zip(years, years[1:]))


def test_event_budget_stays_below_noise_regression_baseline():
    world = World(seed=42)
    world.generate(years=100)
    assert 100 <= len(world.events) < 600


def test_pressure_driven_rebellion_is_reachable_and_has_a_cause():
    world = World(seed=7)
    world.generate(years=100)

    rebellions = [event for event in world.events if event.event_type == "rebellion"]
    assert rebellions
    assert all(event.effects for event in rebellions)
    assert any(event.cause_event_ids for event in rebellions)


def test_disaster_aftermath_can_self_fund_reconstruction():
    world = World(seed=101)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.population = 100
    settlement.treasury = 5000.0
    before_infrastructure = settlement.infrastructure.get("market", 0.0)
    cause = _queue_test_disaster(world, settlement, "flood")

    world.current_year = 3
    world._process_disaster_aftermaths(3)
    aftermath = world.events[-1]

    assert aftermath.event_type == "reconstruction"
    assert aftermath.cause_event_ids == [cause.id]
    assert aftermath.process_id == cause.process_id
    assert aftermath.effects and aftermath.effect_ids
    assert settlement.treasury < 5000.0
    assert settlement.infrastructure["market"] > before_infrastructure


def test_disaster_aftermath_can_transfer_external_aid():
    world = World(seed=102)
    world.generate(years=0)
    recipient, donor = list(world.settlements.values())[:2]
    recipient.population = 100
    recipient.treasury = 0.0
    recipient.food_stock = 0.0
    donor.treasury = 1000.0
    donor.food_stock = 1000.0
    recipient.relationships[donor.id] = RelationshipData(
        partner_id=donor.id, trust=0.8, hostility=0.1)
    donor.relationships[recipient.id] = RelationshipData(
        partner_id=recipient.id, trust=0.8, hostility=0.1)
    treasury_total = recipient.treasury + donor.treasury
    food_total = recipient.food_stock + donor.food_stock
    cause = _queue_test_disaster(world, recipient, "storm")

    world.current_year = 3
    world._process_disaster_aftermaths(3)
    aftermath = world.events[-1]

    assert aftermath.event_type == "relief"
    assert aftermath.cause_event_ids == [cause.id]
    assert set(aftermath.participants) == {recipient.id, donor.id}
    assert recipient.treasury + donor.treasury == treasury_total
    assert recipient.food_stock + donor.food_stock == food_total
    assert recipient.relationships[donor.id].trust > 0.8
    documents = [
        evidence for evidence in world.get_evidence_by_event(aftermath.id)
        if evidence.evidence_type == "document"
    ]
    assert documents
    assert documents[0].content_data["text_plan"]["materialization_status"] \
        == "planned"


def test_disaster_aftermath_can_become_long_term_decline():
    world = World(seed=103)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.population = 100
    settlement.treasury = 0.0
    settlement.relationships.clear()
    before_stability = settlement.stability
    cause = _queue_test_disaster(world, settlement, "earthquake")

    world.current_year = 3
    world._process_disaster_aftermaths(3)
    aftermath = world.events[-1]

    assert aftermath.event_type == "decline"
    assert aftermath.cause_event_ids == [cause.id]
    assert settlement.population == 93
    assert settlement.stability < before_stability


def test_generated_disaster_aftermaths_are_causal_and_reachable():
    world = World(seed=42)
    world.generate(years=100)
    event_by_id = {event.id: event for event in world.events}
    aftermaths = [
        event for event in world.events
        if event.event_type in {"reconstruction", "relief", "decline"}
    ]

    assert aftermaths
    assert {event.event_type for event in aftermaths} <= {
        "reconstruction", "relief", "decline",
    }
    for aftermath in aftermaths:
        assert len(aftermath.cause_event_ids) == 1
        cause = event_by_id[aftermath.cause_event_ids[0]]
        assert cause.event_type == "disaster"
        assert aftermath.year == cause.year + 2
        assert aftermath.process_id == cause.process_id
        assert aftermath.effects and aftermath.effect_ids
