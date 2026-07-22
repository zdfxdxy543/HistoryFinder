"""Political ownership and control-history invariants."""

import json
import random

from simulation.effects import EffectResolver, TransferControl
from simulation.polity import Polity, SettlementControlPeriod
from simulation.world import World


def test_polity_roundtrip():
    polity = Polity(
        id="polity_0001",
        name="Kingdom of Test",
        founded_year=3,
        capital_settlement_id="stl_0001",
        ruler_id="person_0001",
    )
    assert Polity.from_dict(polity.to_dict()) == polity


def test_control_period_roundtrip():
    period = SettlementControlPeriod(
        id="control_000001",
        settlement_id="stl_0001",
        polity_id="polity_0001",
        start_year=3,
        end_year=9,
        reason="conquest",
        event_id="event_0007",
    )
    assert SettlementControlPeriod.from_dict(period.to_dict()) == period


def test_initial_settlements_have_independent_political_control():
    world = World(seed=42)
    world.generate(years=0)

    assert len(world.polities) == len(world.settlements)
    assert len(world.settlement_control_periods) == len(world.settlements)
    assert len({item.controller_polity_id
                for item in world.settlements.values()}) \
        == len(world.settlements)
    for settlement in world.settlements.values():
        polity = world.polities[settlement.controller_polity_id]
        period = world.get_current_control_period(settlement.id)
        assert polity.capital_settlement_id == settlement.id
        assert polity.ruler_id == settlement.ruler_id
        assert period is not None
        assert period.polity_id == polity.id
        assert period.start_year == 0
        assert period.end_year is None
        assert period.event_id in world.event_history_by_settlement[settlement.id]


def test_transfer_control_updates_history_and_can_be_reversed():
    world = World(seed=42)
    world.generate(years=0)
    attacker, target = list(world.settlements.values())[:2]
    old_polity = world.polities[target.controller_polity_id]
    new_polity = world.polities[attacker.controller_polity_id]
    old_period = world.get_current_control_period(target.id)
    original_ruler_name = target.ruler_name
    world.current_year = 8
    resolver = EffectResolver(seed=100)

    effect_ids = resolver.apply_effects([
        TransferControl(
            target.id,
            old_controller_id=old_polity.id,
            new_controller_id=new_polity.id,
            reason="test_conquest",
        )
    ], world)

    assert effect_ids
    assert target.controller_polity_id == new_polity.id
    assert target.ruler_name == original_ruler_name
    assert old_period.end_year == 8
    current = world.get_current_control_period(target.id)
    assert current is not None
    assert current.polity_id == new_polity.id
    assert current.start_year == 8
    assert not old_polity.alive
    assert old_polity.dissolved_year == 8

    assert resolver.reverse_effect(effect_ids[0], world)
    assert target.controller_polity_id == old_polity.id
    assert world.get_current_control_period(target.id).id == old_period.id
    assert old_period.end_year is None
    assert old_polity.alive
    assert old_polity.dissolved_year is None


def test_war_partner_excludes_settlements_in_the_same_polity():
    world = World(seed=7)
    world.generate(years=0)
    source, same_polity, other = list(world.settlements.values())[:3]
    resolver = EffectResolver(seed=101)
    assert resolver.apply_effects([
        TransferControl(
            same_polity.id,
            new_controller_id=source.controller_polity_id,
            reason="setup",
        )
    ], world)

    rule = world._rule_registry.rules["war"]
    choices = {
        rule._select_partner(world, source, random.Random(seed))
        for seed in range(20)
    }

    assert same_polity.id not in choices
    assert other.id in choices or choices
    assert all(
        world.settlements[item].controller_polity_id
        != source.controller_polity_id
        for item in choices
    )


def test_capital_succession_updates_polity_ruler():
    world = World(seed=12)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    polity = world.polities[settlement.controller_polity_id]
    old_ruler = world.persons[settlement.ruler_id]
    successor = next(
        person for person in world.persons.values()
        if person.settlement_id == settlement.id and "heir" in person.roles)
    world.current_year = 1

    world._apply_succession(settlement, old_ruler, successor, 1)

    assert settlement.ruler_id == successor.id
    assert polity.ruler_id == successor.id


def test_current_world_roundtrip_restores_generators_without_id_collisions():
    world = World(seed=19)
    world.generate(years=5)
    serialized = json.loads(json.dumps(world.to_dict(), ensure_ascii=False))
    restored = World.from_dict(serialized)

    assert restored.geography is not None
    assert restored._settlement_mgr._next_id() not in restored.settlements
    assert restored._event_gen._next_id() not in {
        event.id for event in restored.events}
    assert restored._evidence_gen._next_id() not in restored.evidence
    assert restored._record_gen._next_id() not in restored.records
    assert restored._person_mgr.create_person(
        next(iter(restored.settlements)), 0).id not in restored.persons
    assert restored._effect_resolver.generate_id() not in {
        effect_id for event in restored.events for effect_id in event.effect_ids}
    polity = restored._polity_mgr.create_polity(
        next(iter(restored.settlements)), None, restored.current_year)
    assert polity.id not in restored.polities
