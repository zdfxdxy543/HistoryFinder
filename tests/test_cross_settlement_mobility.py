import copy
from types import SimpleNamespace

import pytest

from simulation.effects import (
    DestroySettlement,
    EffectResolver,
    MovePerson,
    StrengthenExchangeNetwork,
    TransferEvidence,
)
from simulation.events import HistoricalEvent
from game.local_map import LocalMapBuilder, build_evidence_targets
from simulation.mobility import (
    exchange_network_status,
    plan_event_exchange_networks,
    plan_supplemental_event_transfers,
    plan_event_transfers,
    select_transfer_candidates,
    settlement_connection_weight,
)
from simulation.world import World
from simulation.text_carriers import materialize_text_carrier


def _world(years: int = 0) -> World:
    world = World(seed=42)
    world.generate(years=years)
    return world


def _event(event_type: str, source_id: str, target_id: str,
           event_id: str = "event_transfer_test") -> HistoricalEvent:
    return HistoricalEvent(
        id=event_id,
        year=1,
        event_type=event_type,
        title="test transfer",
        severity=0.5,
        primary_location=source_id,
        participants=[source_id, target_id],
    )


def _result(outcome: str, target_id: str, effects=None):
    return SimpleNamespace(
        selected_outcome=SimpleNamespace(outcome_type=outcome),
        target_settlement_id=target_id,
        concrete_effects=list(effects or []),
    )


def test_transfer_effect_preserves_origin_and_reverses_custody():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    evidence = next(
        item for item in world.evidence.values()
        if item.location_id == source.id and item.is_copy_of)
    original_history = [dict(item) for item in evidence.location_history]
    resolver = EffectResolver(seed=8)

    effect_ids = resolver.apply_effects([
        TransferEvidence(
            evidence.id,
            target.id,
            transfer_type="war_spoils",
            event_id="event_test_war",
            legitimacy="contested",
            new_owner_id=target.id,
        ),
    ], world)

    assert effect_ids
    assert evidence.origin_location_id == source.id
    assert evidence.location_id == target.id
    assert evidence.owner_id == target.id
    assert source.id in evidence.claimant_ids
    assert evidence.location_history[-1]["event_id"] == "event_test_war"
    assert evidence.location_history[-1]["from_location_id"] == source.id
    assert evidence.location_history[-1]["to_location_id"] == target.id
    assert "provenance:removed_owner_mark" in evidence.physical_features["tags"]

    assert resolver.reverse_effect(effect_ids[0], world)
    assert evidence.location_id == source.id
    assert evidence.owner_id == source.id
    assert evidence.location_history == original_history


def test_trade_plan_moves_a_portable_carrier_and_records_event_details():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    event = _event("trade", source.id, target.id)
    result = _result("trade_opened", target.id)

    plans = plan_event_transfers(world, event, result)

    assert len(plans) == 1
    evidence = world.evidence[plans[0].evidence_id]
    assert evidence.evidence_type in {"document", "artifact"}
    assert event.details["object_transfers"][0]["evidence_id"] == evidence.id
    assert EffectResolver(seed=9).apply_effects(plans, world)
    assert evidence.location_id == target.id
    assert evidence.origin_location_id == source.id
    targets = build_evidence_targets(
        world.evidence.values(), world.storage_sites, target.id)
    assert any(evidence.id in item["evidence_ids"] for item in targets)
    local_map = LocalMapBuilder().build(world, target)
    assert any(
        item["id"] == map_target["id"]
        for map_target in targets
        if evidence.id in map_target["evidence_ids"]
        for item in local_map["entities"]
    )


def test_theft_moves_an_existing_carrier_and_preserves_owner_claim():
    world = _world()
    source = next(iter(world.settlements.values()))
    event = HistoricalEvent(
        id="event_theft_test",
        year=1,
        event_type="crime",
        title=f"{source.name}大盗窃案",
        severity=0.2,
        primary_location=source.id,
        participants=[source.id],
        details={"crime_type": "theft"},
    )

    plans = plan_supplemental_event_transfers(world, event)

    assert len(plans) == 1
    stolen = world.evidence[plans[0].evidence_id]
    original_owner = stolen.owner_id
    assert plans[0].transfer_type == "theft"
    assert EffectResolver(seed=14).apply_effects(plans, world)
    assert stolen.location_id != source.id
    assert original_owner in stolen.claimant_ids
    assert stolen.location_history[-1]["legitimacy"] == "illegal"


def test_disputed_item_is_resold_or_smuggled_instead_of_clean_trade():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    evidence = select_transfer_candidates(
        world, source.id, "trade", "event_resale_test", limit=1)[0]
    evidence.claimant_ids.append(target.id)
    event = _event("trade", source.id, target.id, "event_resale_test")

    plans = plan_event_transfers(
        world, event, _result("trade_opened", target.id))

    assert plans
    assert plans[0].transfer_type in {"smuggling", "resale"}
    assert plans[0].legitimacy in {"illegal", "contested"}
    assert event.details["object_transfers"][0]["transfer_type"] \
        == plans[0].transfer_type


def test_treaty_can_return_an_item_to_a_recorded_claimant():
    world = _world()
    claimant, holder = list(world.settlements.values())[:2]
    evidence = next(
        item for item in world.evidence.values()
        if item.location_id == claimant.id and item.is_copy_of)
    assert EffectResolver(seed=15).apply_effects([
        TransferEvidence(
            evidence.id,
            holder.id,
            transfer_type="theft",
            event_id="event_prior_theft",
            legitimacy="illegal",
            new_owner_id=holder.id,
        )
    ], world)
    event = _event("treaty", holder.id, claimant.id, "event_recovery_test")

    plans = plan_supplemental_event_transfers(world, event)

    assert len(plans) == 1
    assert plans[0].transfer_type == "recovery"
    assert plans[0].target_settlement_id == claimant.id
    assert EffectResolver(seed=16).apply_effects(plans, world)
    assert evidence.location_id == claimant.id
    assert evidence.owner_id == claimant.id
    assert claimant.id not in evidence.claimant_ids


def test_war_victory_moves_spoils_from_loser_to_winner():
    world = _world()
    attacker, defender = list(world.settlements.values())[:2]
    event = _event("war", attacker.id, defender.id)
    result = _result("attacker_victory", defender.id)

    plans = plan_event_transfers(world, event, result)

    assert plans
    assert all(world.evidence[plan.evidence_id].location_id == defender.id
               for plan in plans)
    assert EffectResolver(seed=10).apply_effects(plans, world)
    assert all(world.evidence[plan.evidence_id].location_id == attacker.id
               for plan in plans)
    assert all(world.evidence[plan.evidence_id].owner_id == attacker.id
               for plan in plans)


def test_event_without_a_transfer_does_not_gain_an_empty_transfer_field():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    event = _event("disaster", source.id, target.id)
    event.details["object_transfers"] = []

    plans = plan_event_transfers(
        world, event, _result("minor_earthquake", None))

    assert plans == []
    assert "object_transfers" not in event.details


def test_catastrophic_destruction_evacuates_material_before_ruin_processing():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    event = _event("disaster", source.id, target.id)
    destroy = DestroySettlement(source.id, cause="earthquake")
    result = _result("catastrophic_earthquake", None, [destroy])

    plans = plan_event_transfers(world, event, result)
    evacuated_ids = {plan.evidence_id for plan in plans}
    destination_ids = {plan.target_settlement_id for plan in plans}

    assert evacuated_ids
    assert len(destination_ids) == 1
    destination_id = next(iter(destination_ids))
    destination_site_id = world._storage_mgr._site_id(
        destination_id, "private_collection")
    assert destination_site_id not in world.storage_sites
    settlement_before = {
        "alive": source.alive,
        "destroyed_year": source.destroyed_year,
        "destruction_cause": source.destruction_cause,
        "population": source.population,
    }
    evidence_before = {
        item_id: {
            "location_id": world.evidence[item_id].location_id,
            "container_id": world.evidence[item_id].container_id,
            "holder_type": world.evidence[item_id].holder_type,
            "holder_id": world.evidence[item_id].holder_id,
            "owner_type": world.evidence[item_id].owner_type,
            "owner_id": world.evidence[item_id].owner_id,
            "claimant_ids": list(world.evidence[item_id].claimant_ids),
            "location_history": copy.deepcopy(
                world.evidence[item_id].location_history),
        }
        for item_id in evacuated_ids
    }
    resolver = EffectResolver(seed=11)
    effect_ids = resolver.apply_effects(plans + [destroy], world)

    assert effect_ids
    assert not source.alive
    assert destination_site_id in world.storage_sites
    assert all(world.evidence[item_id].location_id in destination_ids
               for item_id in evacuated_ids)
    assert all(world.evidence[item_id].state != "destroyed"
               for item_id in evacuated_ids)

    for effect_id in reversed(effect_ids):
        assert resolver.reverse_effect(effect_id, world)

    assert {
        "alive": source.alive,
        "destroyed_year": source.destroyed_year,
        "destruction_cause": source.destruction_cause,
        "population": source.population,
    } == settlement_before
    assert destination_site_id not in world.storage_sites
    for item_id, before in evidence_before.items():
        evidence = world.evidence[item_id]
        assert evidence.location_id == before["location_id"]
        assert evidence.container_id == before["container_id"]
        assert evidence.holder_type == before["holder_type"]
        assert evidence.holder_id == before["holder_id"]
        assert evidence.owner_type == before["owner_type"]
        assert evidence.owner_id == before["owner_id"]
        assert evidence.claimant_ids == before["claimant_ids"]
        assert evidence.location_history == before["location_history"]


def test_distance_reduces_connection_weight_when_relationships_match():
    world = _world()
    source = next(iter(world.settlements.values()))
    others = sorted(
        (item for item in world.settlements.values() if item.id != source.id),
        key=lambda item: (
            (item.grid_x - source.grid_x) ** 2
            + (item.grid_y - source.grid_y) ** 2,
            item.id,
        ),
    )
    near, far = others[0], others[-1]

    assert settlement_connection_weight(world, source, near, "trade") \
        > settlement_connection_weight(world, source, far, "trade")


def test_exchange_network_effect_is_bilateral_and_reversible():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    source_relationship = source.relationships.get(target.id)
    target_relationship = target.relationships.get(source.id)
    before_source = (
        copy.deepcopy(source_relationship.to_dict())
        if source_relationship is not None else None)
    before_target = (
        copy.deepcopy(target_relationship.to_dict())
        if target_relationship is not None else None)
    resolver = EffectResolver(seed=12)
    world.current_year = 7

    effect_ids = resolver.apply_effects([
        StrengthenExchangeNetwork(
            source.id, target.id, "scholarly", 0.34,
            event_id="event_network_test", topic_key="mechanics")
    ], world)

    assert effect_ids
    for relationship in (
            source.relationships[target.id], target.relationships[source.id]):
        assert relationship.exchange_counts["scholarly"] == 1
        assert relationship.exchange_strengths["scholarly"] == 0.34
        assert relationship.exchange_last_years["scholarly"] == 7
        assert relationship.exchange_topics["scholarly"] == ["mechanics"]
    assert resolver.reverse_effect(effect_ids[0], world)
    restored_source = source.relationships.get(target.id)
    restored_target = target.relationships.get(source.id)
    assert (restored_source.to_dict()
            if restored_source is not None else None) == before_source
    assert (restored_target.to_dict()
            if restored_target is not None else None) == before_target


def test_repeated_visits_form_a_stable_network_and_raise_route_weight():
    world = _world()
    source, target = list(world.settlements.values())[:2]
    merchant = next(
        world.persons[informant.person_id]
        for informant in world.informants.values()
        if informant.role == "merchant"
        and world.persons[informant.person_id].current_location_id == source.id)
    movement = MovePerson(
        merchant.id, target.id, "trade_visit",
        mobility_status="visitor", travel_role="merchant",
        stay_until_year=2,
    )
    event = _event("trade", source.id, target.id, "event_network_growth")
    weight_before = settlement_connection_weight(
        world, source, target, "trade")
    statuses = []
    resolver = EffectResolver(seed=13)

    for year in range(1, 7):
        world.current_year = year
        effects, details = plan_event_exchange_networks(
            world, event, [movement], [])
        assert resolver.apply_effects(effects, world)
        statuses.append(details[0]["status_after"])

    relationship = source.relationships[target.id]
    assert relationship.exchange_counts["trade"] == 6
    assert relationship.exchange_strengths["trade"] == pytest.approx(1.68)
    assert "regular" in statuses
    assert statuses[-1] == "established"
    assert exchange_network_status(
        relationship.exchange_strengths["trade"]) == "established"
    assert settlement_connection_weight(world, source, target, "trade") \
        > weight_before


def test_network_status_transition_is_preserved_in_written_evidence():
    world = _world(20)
    event = next(
        item for item in world.events
        if item.event_type in {"discovery", "theoretical_work", "trade"}
        and any(update["status_before"] != update["status_after"]
                for update in item.details.get("network_updates", [])))
    document = next(
        item for item in world.evidence.values()
        if item.event_id == event.id and item.evidence_type == "document"
        and not item.is_copy_of)

    materialize_text_carrier(world, document.id)
    text = "\n".join(
        passage["text"]
        for passage in document.content_data["written_content"]["passages"])
    record = world.records[document.source_record_id]

    assert "往来附记" in text
    assert any(claim.predicate == "exchange_network_formed"
               for claim in record.claimed_facts)


def test_transfer_state_roundtrips_and_is_deterministic():
    first = _world(30)
    second = _world(30)
    first_transfers = {
        item.id: item.location_history
        for item in first.evidence.values()
        if any(entry.get("event_id") for entry in item.location_history)
    }
    second_transfers = {
        item.id: item.location_history
        for item in second.evidence.values()
        if any(entry.get("event_id") for entry in item.location_history)
    }

    assert first_transfers
    assert first_transfers == second_transfers
    restored = World.from_dict(first.to_dict())
    for evidence_id in first_transfers:
        before = first.evidence[evidence_id]
        after = restored.evidence[evidence_id]
        assert after.origin_location_id == before.origin_location_id
        assert after.owner_id == before.owner_id
        assert after.claimant_ids == before.claimant_ids
        assert after.location_history == before.location_history


def test_trade_ledger_names_the_transferred_item_and_destination():
    world = _world(10)
    event = next(
        item for item in world.events
        if item.event_type == "trade" and item.details.get("object_transfers"))
    transfer = event.details["object_transfers"][0]
    ledger = next(
        item for item in world.evidence.values()
        if item.event_id == event.id and item.subtype == "trade_ledger")

    materialize_text_carrier(world, ledger.id)
    text = "\n".join(
        passage["text"]
        for passage in ledger.content_data["written_content"]["passages"])
    record = world.records[ledger.source_record_id]

    assert transfer["evidence_name"] in text
    assert transfer["to_location_name"] in text
    assert any(claim.predicate == "object_transferred"
               for claim in record.claimed_facts)
