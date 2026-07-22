"""Deterministic cross-settlement movement for important physical carriers."""

from __future__ import annotations

import hashlib
import math

from simulation.effects import (
    DestroySettlement,
    KillPerson,
    MarkRuinSurvivor,
    ModifyCulturalInfluence,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
    MovePerson,
    RelocatePopulation,
    StrengthenExchangeNetwork,
    TransferEvidence,
)
from simulation.technology import (
    TECHNOLOGY_ARTIFACT_SUBTYPES,
    TECHNOLOGY_BY_SUBTYPE,
)
from simulation.written_content import PUBLIC_INSCRIPTION_SUBTYPES


def settlement_connection_weight(world, source, target,
                                 purpose: str) -> float:
    """Return a positive route weight shaped by distance and relations."""
    distance = math.hypot(
        target.grid_x - source.grid_x,
        target.grid_y - source.grid_y,
    )
    geography = getattr(world, "geography", None)
    diagonal = math.hypot(
        getattr(geography, "width", 64),
        getattr(geography, "height", 64),
    )
    distance_factor = max(0.04, 1.0 - distance / max(diagonal, 1.0)) ** 2
    relationship = source.relationships.get(target.id)
    trust = relationship.trust if relationship else 0.5
    hostility = relationship.hostility if relationship else 0.1
    trade_volume = relationship.trade_volume if relationship else 0.0
    if purpose == "war":
        social = 0.06 + hostility ** 2 * 2.4
    elif purpose == "refuge":
        cultural_tie = relationship.exchange_strengths.get(
            "cultural", 0.0) if relationship else 0.0
        social = max(
            0.05,
            0.25 + trust * 1.3 - hostility * 0.8
            + min(cultural_tie * 0.04, 0.35),
        )
    else:
        trade_tie = relationship.exchange_strengths.get(
            "trade", 0.0) if relationship else 0.0
        scholarly_tie = relationship.exchange_strengths.get(
            "scholarly", 0.0) if relationship else 0.0
        cultural_tie = relationship.exchange_strengths.get(
            "cultural", 0.0) if relationship else 0.0
        network_bonus = min(
            trade_tie * 0.18 + scholarly_tie * 0.08
            + cultural_tie * 0.05,
            1.2,
        )
        social = (
            0.12 + trust + min(trade_volume / 120.0, 1.2)
            + network_bonus)
    return max(0.001, distance_factor * social)


def _stable_tiebreak(seed: int, event_id: str, evidence_id: str) -> int:
    digest = hashlib.sha256(
        f"{seed}|mobility|{event_id}|{evidence_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _portable_score(world, evidence, transfer_type: str) -> float:
    if evidence.state in {"buried", "destroyed"}:
        return 0.0
    if evidence.evidence_type not in {"artifact", "document"}:
        return 0.0
    subtype = evidence.subtype.removesuffix("_copy")
    if subtype in PUBLIC_INSCRIPTION_SUBTYPES:
        return 0.0
    site = world.storage_sites.get(evidence.container_id)
    if site is not None and site.site_type in {"field_site", "monument_site"}:
        return 0.0

    technology = subtype in TECHNOLOGY_ARTIFACT_SUBTYPES
    if transfer_type == "trade":
        if evidence.evidence_type == "document" and not evidence.is_copy_of:
            return 0.0
        score = 7.0 if technology else 4.0 if evidence.is_copy_of else 2.0
        if site is not None and site.site_type in {
                "merchant_archive", "workshop_store", "private_collection"}:
            score += 1.5
        return score
    if transfer_type == "war_spoils":
        score = 6.0 if evidence.material == "metal" else 3.0
        if evidence.evidence_type == "document":
            score += 2.0
        if site is not None and site.site_type in {
                "temple_repository", "administrative_archive",
                "private_collection"}:
            score += 1.5
        return score
    if transfer_type == "evacuation":
        score = 7.0 if evidence.evidence_type == "document" else 3.0
        if technology:
            score += 2.0
        if site is not None and site.site_type == "private_collection":
            score += 1.0
        return score
    if transfer_type == "theft":
        score = 7.0 if technology else 4.0
        if evidence.material == "metal":
            score += 2.0
        if site is not None and site.site_type in {
                "private_collection", "temple_repository",
                "administrative_archive", "workshop_store"}:
            score += 1.5
        return score
    return 0.0


def select_transfer_candidates(world, source_id: str, transfer_type: str,
                               event_id: str, limit: int = 1) -> list:
    candidates = []
    for evidence in world.evidence.values():
        if evidence.location_id != source_id:
            continue
        score = _portable_score(world, evidence, transfer_type)
        if score <= 0:
            continue
        candidates.append((
            -score,
            _stable_tiebreak(world.seed, event_id, evidence.id),
            evidence.id,
            evidence,
        ))
    candidates.sort(key=lambda item: item[:3])
    return [item[3] for item in candidates[:limit]]


def best_refuge_destination(world, source_id: str):
    destinations = refuge_destinations(world, source_id, limit=1)
    return destinations[0] if destinations else None


def refuge_destinations(world, source_id: str, limit: int = 2) -> list:
    source = world.settlements.get(source_id)
    if source is None:
        return []
    candidates = [
        settlement for settlement in world.settlements.values()
        if settlement.alive and settlement.id != source_id
    ]
    candidates.sort(key=lambda target: (
        settlement_connection_weight(world, source, target, "refuge"),
        -math.hypot(target.grid_x - source.grid_x,
                    target.grid_y - source.grid_y),
        target.id,
    ), reverse=True)
    return candidates[:limit]


def best_exchange_destination(world, source_id: str, event_id: str):
    """Choose a living partner for a deterministic knowledge visit."""
    source = world.settlements.get(source_id)
    if source is None or not source.alive:
        return None
    candidates = [
        target for target in world.settlements.values()
        if target.alive and target.id != source_id
    ]
    candidates.sort(key=lambda target: (
        -settlement_connection_weight(world, source, target, "trade"),
        _stable_tiebreak(world.seed, event_id, target.id),
        target.id,
    ))
    return candidates[0] if candidates else None


def plan_event_transfers(world, event, result) -> list[TransferEvidence]:
    """Plan portable-object effects before the event transaction is applied."""
    outcome = result.selected_outcome.outcome_type
    target_id = result.target_settlement_id
    plans: list[TransferEvidence] = []
    if event.event_type == "trade" and target_id:
        selected = select_transfer_candidates(
            world, event.primary_location, "trade", event.id, limit=1)
        for evidence in selected:
            if evidence.claimant_ids:
                discriminator = _stable_tiebreak(
                    world.seed, event.id, evidence.id) % 2
                transfer_type = "smuggling" if discriminator == 0 else "resale"
                legitimacy = "illegal" if discriminator == 0 else "contested"
                site_type = "private_collection"
            else:
                transfer_type = "trade"
                legitimacy = "legal"
                site_type = "merchant_archive"
            plans.extend(_effects_for(
                [evidence], target_id, event.id, transfer_type, legitimacy,
                site_type, new_owner=True))
    elif event.event_type == "war" and target_id:
        if outcome == "attacker_victory":
            source_id, destination_id = target_id, event.primary_location
        elif outcome == "defender_victory":
            source_id, destination_id = event.primary_location, target_id
        else:
            source_id = destination_id = ""
        if source_id:
            selected = select_transfer_candidates(
                world, source_id, "war_spoils", event.id, limit=2)
            plans.extend(_effects_for(
                selected, destination_id, event.id, "war_spoils",
                "contested", "private_collection", new_owner=True))

    if any(isinstance(effect, DestroySettlement)
           for effect in result.concrete_effects):
        refuge = best_refuge_destination(world, event.primary_location)
        if refuge is not None:
            selected = select_transfer_candidates(
                world, event.primary_location, "evacuation", event.id, limit=2)
            plans.extend(_effects_for(
                selected, refuge.id, event.id, "evacuation", "emergency",
                "private_collection", new_owner=False))

    _attach_transfer_details(world, event, plans)
    return plans


def plan_supplemental_event_transfers(world, event) -> list[TransferEvidence]:
    """Plan transfers for ambient crimes and non-rule treaty events."""
    if event.details.get("object_transfers"):
        return []
    plans: list[TransferEvidence] = []
    if (event.event_type == "crime"
            and event.details.get("crime_type") == "theft"):
        target = best_exchange_destination(
            world, event.primary_location, event.id)
        if target is not None:
            selected = select_transfer_candidates(
                world, event.primary_location, "theft", event.id, limit=1)
            plans.extend(_effects_for(
                selected, target.id, event.id, "theft", "illegal",
                "private_collection", new_owner=True))
            if target.id not in event.participants:
                event.participants.append(target.id)
    elif event.event_type == "treaty":
        participant_ids = {
            item for item in event.participants if item in world.settlements}
        candidates = []
        for evidence in world.evidence.values():
            if (evidence.location_id not in participant_ids
                    or evidence.state in {"buried", "destroyed"}):
                continue
            claimant = next((
                item for item in evidence.claimant_ids
                if item in participant_ids and item != evidence.location_id
            ), None)
            if claimant is None:
                continue
            candidates.append((
                _stable_tiebreak(world.seed, event.id, evidence.id),
                evidence.id, evidence, claimant))
        if candidates:
            _, _, evidence, claimant = sorted(candidates)[0]
            plans.append(TransferEvidence(
                evidence_id=evidence.id,
                target_settlement_id=claimant,
                target_site_type="administrative_archive",
                transfer_type="recovery",
                event_id=event.id,
                legitimacy="recovered",
                new_owner_type="settlement",
                new_owner_id=claimant,
                resolved_claimant_id=claimant,
                reason=f"recovery:{event.id}",
            ))

    _attach_transfer_details(world, event, plans)
    return plans


def _attach_transfer_details(world, event, plans) -> None:
    if not plans:
        event.details.pop("object_transfers", None)
        return
    event.details["object_transfers"] = [
        {
            "evidence_id": plan.evidence_id,
            "evidence_name": world.evidence[
                plan.evidence_id].physical_features.get(
                    "display_name", world.evidence[plan.evidence_id].subtype),
            "from_location_id": world.evidence[plan.evidence_id].location_id,
            "from_location_name": world.settlements[
                world.evidence[plan.evidence_id].location_id].name,
            "to_location_id": plan.target_settlement_id,
            "to_location_name": world.settlements[
                plan.target_settlement_id].name,
            "transfer_type": plan.transfer_type,
            "legitimacy": plan.legitimacy,
        }
        for plan in plans
    ]


def _effects_for(evidence_items, target_id: str, event_id: str,
                 transfer_type: str, legitimacy: str, site_type: str,
                 *, new_owner: bool) -> list[TransferEvidence]:
    return [
        TransferEvidence(
            evidence_id=evidence.id,
            target_settlement_id=target_id,
            target_site_type=site_type,
            transfer_type=transfer_type,
            event_id=event_id,
            legitimacy=legitimacy,
            new_owner_type="settlement" if new_owner else None,
            new_owner_id=target_id if new_owner else None,
            reason=f"{transfer_type}:{event_id}",
        )
        for evidence in evidence_items
    ]


def plan_event_person_movements(world, event) -> list:
    """Plan event-linked travel after the event's core effects succeed."""
    participants = [
        item for item in event.participants if item in world.settlements]
    carried_by_type = _carried_evidence_by_type(event)

    if event.event_type == "trade" and len(participants) >= 2:
        source_id = event.primary_location
        target_id = next(
            (item for item in participants if item != source_id), "")
        merchant = _select_local_informants(
            world, source_id, event.id, ("merchant",), limit=1)
        return _person_effects(
            merchant, target_id, event, "trade_visit", "visitor",
            "merchant", 2, 6, [
                *carried_by_type.get("trade", []),
                *carried_by_type.get("resale", []),
                *carried_by_type.get("smuggling", []),
            ])

    if event.event_type == "war" and len(participants) >= 2:
        outcome = event.details.get(
            "outcome", event.details.get("outcome_type", ""))
        attacker_id = event.primary_location
        defender_id = next(
            (item for item in participants if item != attacker_id), "")
        if outcome == "attacker_victory":
            source_id, target_id = defender_id, attacker_id
        elif outcome == "defender_victory":
            source_id, target_id = attacker_id, defender_id
        else:
            return []
        captive = _select_local_informants(
            world, source_id, event.id,
            ("artisan", "scribe", "merchant", "scholar"), limit=1)
        return _person_effects(
            captive, target_id, event, "captive_transfer", "captive",
            "captive", None, None,
            carried_by_type.get("war_spoils", []))

    if event.event_type == "treaty" and len(participants) >= 2:
        target_id = event.primary_location
        source_id = next(
            (item for item in participants if item != target_id), "")
        envoy = _select_local_informants(
            world, source_id, event.id, ("scribe", "merchant"), limit=1)
        return _person_effects(
            envoy, target_id, event, "diplomatic_mission", "envoy",
            "envoy", 1, 3, [])

    if event.event_type == "disaster" and _destroyed_by_event(event):
        return _plan_disaster_person_outcomes(
            world, event, carried_by_type.get("evacuation", []))

    if event.event_type in {"discovery", "theoretical_work"}:
        target = best_exchange_destination(
            world, event.primary_location, event.id)
        if target is None:
            return []
        visitors = _select_local_informants(
            world, event.primary_location, event.id,
            ("scholar", "scribe"), limit=1)
        movement_type = {
            "discovery": "technology_demonstration",
            "theoretical_work": "scholarly_lecture",
        }[event.event_type]
        if target.id not in event.participants:
            event.participants.append(target.id)
        return _person_effects(
            visitors, target.id, event, movement_type,
            "visitor", "visiting_scholar", 2, 5, [])

    if event.event_type == "literary_work":
        visitor = _select_external_informant(
            world, event.primary_location, event.id,
            ("scholar", "scribe"))
        return _person_effects(
            visitor, event.primary_location, event, "scholarly_visit",
            "visitor", "visiting_scholar", 2, 5, [])

    if event.event_type == "literary_spread" and len(participants) >= 2:
        target_id = event.primary_location
        source_id = next(
            (item for item in participants if item != target_id), "")
        visitor = _select_local_informants(
            world, source_id, event.id, ("scribe", "scholar"), limit=1)
        return _person_effects(
            visitor, target_id, event, "manuscript_delivery", "visitor",
            "visiting_scholar", 2, 4, [])

    return []


def plan_event_knowledge_transfers(world, event,
                                   person_effects: list[MovePerson]
                                   ) -> tuple[list, list[dict]]:
    """Turn event-linked travel into grounded settlement-level diffusion."""
    effects = []
    details = []
    for movement in person_effects:
        if not isinstance(movement, MovePerson):
            continue
        person = world.persons.get(movement.person_id)
        source = world.settlements.get(
            person.current_location_id if person is not None else "")
        target = world.settlements.get(movement.target_settlement_id)
        if person is None or source is None or target is None:
            continue

        if movement.movement_type == "trade_visit":
            for transfer in event.details.get("object_transfers", []):
                if transfer.get("transfer_type") not in {
                        "trade", "resale", "smuggling"}:
                    continue
                evidence = world.evidence.get(transfer.get("evidence_id", ""))
                if evidence is None:
                    continue
                classification = _classify_carried_knowledge(world, evidence)
                if classification is None:
                    continue
                dimension, topic_key, topic_name, source_event_id = \
                    classification
                _append_diffusion(
                    effects, details, source, target, person, dimension,
                    topic_key, topic_name, source_event_id,
                    evidence.id, "trade_carriage", base_delta={
                        "technology": 0.12,
                        "theory": 0.10,
                        "culture": 0.08,
                    }[dimension])

        elif movement.movement_type == "technology_demonstration":
            _append_diffusion(
                effects, details, source, target, person, "technology",
                event.details.get("technology_key", "applied_technology"),
                event.details.get("discovery_name", event.title),
                event.id, "", "technology_demonstration", 0.16)
        elif movement.movement_type == "scholarly_lecture":
            _append_diffusion(
                effects, details, source, target, person, "theory",
                event.details.get("theory_field", "natural_philosophy"),
                event.details.get("theory_field_name", event.title),
                event.id, "", "scholarly_lecture", 0.14)
        elif movement.movement_type == "manuscript_delivery":
            details.append(_diffusion_detail(
                source, target, person, "culture",
                event.details.get("genre", "literature"),
                event.details.get("work_title", event.title),
                event.cause_event_ids[0] if event.cause_event_ids else event.id,
                "", "manuscript_delivery", 0.18))
    return effects, details


def exchange_network_status(strength: float) -> str:
    if strength >= 1.5:
        return "established"
    if strength >= 0.5:
        return "regular"
    return "nascent"


def plan_event_exchange_networks(world, event,
                                 person_effects: list,
                                 knowledge_details: list[dict]
                                 ) -> tuple[list, list[dict]]:
    """Accumulate repeated travel into persistent bilateral networks."""
    effects = []
    details = []
    seen = set()
    movement_profiles = {
        "trade_visit": ("trade", 0.28),
        "technology_demonstration": ("scholarly", 0.34),
        "scholarly_lecture": ("scholarly", 0.34),
        "scholarly_visit": ("cultural", 0.12),
        "manuscript_delivery": ("cultural", 0.36),
    }
    for movement in person_effects:
        if not isinstance(movement, MovePerson):
            continue
        profile = movement_profiles.get(movement.movement_type)
        person = world.persons.get(movement.person_id)
        if profile is None or person is None:
            continue
        source = world.settlements.get(person.current_location_id)
        target = world.settlements.get(movement.target_settlement_id)
        if source is None or target is None or source.id == target.id:
            continue
        channel, amount = profile
        key = tuple(sorted((source.id, target.id))) + (channel,)
        if key in seen:
            continue
        seen.add(key)
        linked_knowledge = next((
            item for item in knowledge_details
            if item.get("person_id") == person.id
            and item.get("target_location_id") == target.id
        ), None)
        topic_key = (
            linked_knowledge.get("topic_key", "")
            if linked_knowledge is not None else _movement_topic(event))
        relationship = source.relationships.get(target.id)
        before = (
            relationship.exchange_strengths.get(channel, 0.0)
            if relationship is not None else 0.0)
        after = round(min(10.0, before + amount), 3)
        effects.append(StrengthenExchangeNetwork(
            source.id,
            target.id,
            channel,
            amount,
            event_id=event.id,
            topic_key=topic_key,
        ))
        details.append({
            "channel": channel,
            "source_location_id": source.id,
            "source_location_name": source.name,
            "target_location_id": target.id,
            "target_location_name": target.name,
            "person_id": person.id,
            "person_name": person.name,
            "movement_type": movement.movement_type,
            "topic_key": topic_key,
            "strength_before": before,
            "strength_after": after,
            "status_before": exchange_network_status(before),
            "status_after": exchange_network_status(after),
        })
    return effects, details


def _movement_topic(event) -> str:
    if event.event_type in {"literary_work", "literary_spread"}:
        return event.details.get("work_title", "literature")
    if event.event_type == "theoretical_work":
        return event.details.get("theory_field", "natural_philosophy")
    if event.event_type == "discovery":
        return event.details.get("technology_key", "applied_technology")
    return event.event_type


def _classify_carried_knowledge(world, evidence):
    subtype = evidence.subtype.removesuffix("_copy")
    if subtype in TECHNOLOGY_BY_SUBTYPE:
        profile = TECHNOLOGY_BY_SUBTYPE[subtype]
        source_event_id = _source_event_id(world, evidence)
        return "technology", profile.key, profile.title, source_event_id

    source_event_id = _source_event_id(world, evidence)
    source_event = world.get_event(source_event_id) if source_event_id else None
    if source_event is None:
        return None
    if source_event.event_type == "theoretical_work":
        return (
            "theory",
            source_event.details.get("theory_field", "natural_philosophy"),
            source_event.details.get("theory_field_name", source_event.title),
            source_event.id,
        )
    if source_event.event_type in {"literary_work", "literary_spread"}:
        return (
            "culture",
            source_event.details.get("genre", "literature"),
            source_event.details.get("work_title", source_event.title),
            source_event.id,
        )
    return None


def _source_event_id(world, evidence) -> str:
    record = world.records.get(evidence.source_record_id)
    if record is None or not record.source_event_ids:
        return evidence.event_id or ""
    return record.source_event_ids[0]


def _append_diffusion(effects: list, details: list[dict], source, target,
                      person, dimension: str, topic_key: str,
                      topic_name: str, source_event_id: str,
                      source_evidence_id: str, transfer_type: str,
                      base_delta: float) -> None:
    before = _dimension_value(target, dimension)
    source_value = _dimension_value(source, dimension)
    gap_bonus = min(max(source_value - before, 0.0) * 0.03, 0.08)
    delta = round(min(base_delta + gap_bonus, 10.0 - before), 3)
    if delta <= 0:
        return
    reason = f"knowledge_diffusion:{transfer_type}:{source.id}"
    if dimension == "technology":
        effects.append(ModifyTechnologyLevel(target.id, delta, reason))
    elif dimension == "theory":
        effects.append(ModifyTheoreticalKnowledge(target.id, delta, reason))
    else:
        effects.append(ModifyCulturalInfluence(target.id, delta, reason))
    details.append(_diffusion_detail(
        source, target, person, dimension, topic_key, topic_name,
        source_event_id, source_evidence_id, transfer_type, delta))


def _dimension_value(settlement, dimension: str) -> float:
    return {
        "technology": settlement.technology_level,
        "theory": settlement.theoretical_knowledge,
        "culture": settlement.cultural_influence,
    }[dimension]


def _diffusion_detail(source, target, person, dimension: str,
                      topic_key: str, topic_name: str,
                      source_event_id: str, source_evidence_id: str,
                      transfer_type: str, delta: float) -> dict:
    return {
        "dimension": dimension,
        "topic_key": topic_key,
        "topic_name": topic_name,
        "source_event_id": source_event_id,
        "source_evidence_id": source_evidence_id,
        "source_location_id": source.id,
        "source_location_name": source.name,
        "target_location_id": target.id,
        "target_location_name": target.name,
        "person_id": person.id,
        "person_name": person.name,
        "transfer_type": transfer_type,
        "delta": delta,
    }


def describe_person_movements(world, effects: list) -> list[dict]:
    """Build persisted event details after movement effects are applied."""
    result = []
    for effect in effects:
        person = world.persons[effect.person_id]
        history = person.movement_history[-1]
        source_id = history["from_location_id"]
        target_id = history["to_location_id"]
        result.append({
            "person_id": person.id,
            "person_name": person.name,
            "home_location_id": person.settlement_id,
            "from_location_id": source_id,
            "from_location_name": world.settlements[source_id].name,
            "to_location_id": target_id,
            "to_location_name": world.settlements[target_id].name,
            "movement_type": history["movement_type"],
            "mobility_status": history["mobility_status"],
            "travel_role": history["travel_role"],
            "stay_until_year": history.get("stay_until_year"),
            "carried_evidence_ids": list(
                history.get("carried_evidence_ids", [])),
        })
    return result


def plan_disaster_population_displacement(world, event) -> tuple[list, dict]:
    """Move most aggregate survivors while retaining a small ruin camp."""
    if event.event_type != "disaster" or not _destroyed_by_event(event):
        return [], {}
    source = world.settlements.get(event.primary_location)
    if source is None or source.alive or source.population <= 0:
        return [], {}
    destinations = refuge_destinations(world, source.id, limit=2)
    if not destinations:
        return [], {
            "survivors_after_destruction": source.population,
            "remaining_at_ruins": source.population,
            "destinations": [],
        }
    survivors = source.population
    displaced = int(survivors * 0.8)
    remaining = survivors - displaced
    counts = [displaced // len(destinations)] * len(destinations)
    for index in range(displaced % len(destinations)):
        counts[index] += 1
    effects = [
        RelocatePopulation(
            source.id, destination.id, count,
            reason=f"refugees_from:{source.id}")
        for destination, count in zip(destinations, counts)
        if count > 0
    ]
    return effects, {
        "survivors_after_destruction": survivors,
        "remaining_at_ruins": remaining,
        "destinations": [
            {
                "location_id": destination.id,
                "location_name": destination.name,
                "population": count,
            }
            for destination, count in zip(destinations, counts)
            if count > 0
        ],
    }


def _plan_disaster_person_outcomes(world, event, carried_ids: list[str]) -> list:
    source_id = event.primary_location
    present = sorted((
        person for person in world.persons.values()
        if person.alive and person.current_location_id == source_id
    ), key=lambda person: person.id)
    if not present:
        return []
    destinations = refuge_destinations(world, source_id, limit=2)
    local_people = [
        person for person in present if person.settlement_id == source_id]
    visitors = [
        person for person in present if person.settlement_id != source_id]
    protected_ids = {
        settlement.ruler_id
        for settlement in world.settlements.values()
        if settlement.alive and settlement.id != source_id
        and settlement.ruler_id
    }
    casualty_candidates = [
        person for person in local_people
        if person.id not in protected_ids
        and not {"ruler", "heir"}.intersection(person.roles)
    ]
    casualty_candidates.sort(key=lambda person: (
        _stable_tiebreak(world.seed, event.id, person.id), person.id))
    casualty_count = (
        min(len(casualty_candidates), max(1, len(local_people) // 5))
        if len(local_people) >= 5 else 0)
    casualties = casualty_candidates[:casualty_count]
    casualty_ids = {person.id for person in casualties}
    remaining = [
        person for person in local_people if person.id not in casualty_ids]

    registered = {
        informant.person_id for informant in world.informants.values()}
    informant_survivors = [
        person for person in remaining if person.id in registered]
    informant_survivors.sort(key=lambda person: (
        _stable_tiebreak(world.seed, event.id, person.id), person.id))
    others = [person for person in remaining if person.id not in registered]
    others.sort(key=lambda person: (
        _stable_tiebreak(world.seed, event.id, person.id), person.id))
    survivor_count = min(2, max(1, len(remaining) // 6)) if remaining else 0
    ruin_survivors = (informant_survivors[:1] + others)[:survivor_count]
    if len(ruin_survivors) < survivor_count:
        selected = {person.id for person in ruin_survivors}
        ruin_survivors.extend(
            person for person in informant_survivors
            if person.id not in selected
        )
        ruin_survivors = ruin_survivors[:survivor_count]
    ruin_survivor_ids = {person.id for person in ruin_survivors}
    refugees = [
        person for person in remaining
        if person.id not in ruin_survivor_ids]

    effects: list = [
        KillPerson(
            person.id,
            cause=world.settlements[source_id].destruction_cause or "disaster",
            event_id=event.id,
            death_year=event.year,
        )
        for person in casualties
    ]
    effects.extend(
        MarkRuinSurvivor(
            person.id, source_id, event_id=event.id, year=event.year)
        for person in ruin_survivors
    )

    if destinations:
        for index, person in enumerate(refugees):
            destination = destinations[index % len(destinations)]
            carried = [
                evidence_id for offset, evidence_id in enumerate(carried_ids)
                if offset % max(len(refugees), 1) == index
            ]
            effects.append(MovePerson(
                person.id,
                destination.id,
                "forced_displacement",
                event_id=event.id,
                movement_year=event.year,
                mobility_status="displaced",
                travel_role="refugee",
                carried_evidence_ids=carried,
            ))
    else:
        effects.extend(
            MarkRuinSurvivor(
                person.id, source_id, event_id=event.id, year=event.year)
            for person in refugees
        )

    for person in visitors:
        home = world.settlements.get(person.settlement_id)
        if home is not None and home.alive:
            effects.append(MovePerson(
                person.id,
                home.id,
                "evacuation_return",
                event_id=event.id,
                movement_year=event.year,
                mobility_status="resident",
                travel_role="",
            ))
        elif destinations:
            effects.append(MovePerson(
                person.id,
                destinations[0].id,
                "forced_displacement",
                event_id=event.id,
                movement_year=event.year,
                mobility_status="displaced",
                travel_role="refugee",
            ))
    return effects


def _select_local_informants(world, source_id: str, event_id: str,
                              roles: tuple[str, ...], limit: int) -> list:
    role_priority = {role: index for index, role in enumerate(roles)}
    candidates = []
    for informant in world.informants.values():
        if informant.role not in role_priority:
            continue
        person = world.persons.get(informant.person_id)
        if person is None or not person.alive:
            continue
        if person.current_location_id != source_id:
            continue
        if person.mobility_status != "resident":
            continue
        if {"ruler", "heir"}.intersection(person.roles):
            continue
        candidates.append((
            role_priority[informant.role],
            _stable_tiebreak(world.seed, event_id, person.id),
            person.id,
            person,
        ))
    candidates.sort(key=lambda item: item[:3])
    return [item[3] for item in candidates[:limit]]


def _select_external_informant(world, target_id: str, event_id: str,
                               roles: tuple[str, ...]) -> list:
    target = world.settlements.get(target_id)
    if target is None:
        return []
    candidates = []
    for source in world.settlements.values():
        if not source.alive or source.id == target_id:
            continue
        people = _select_local_informants(
            world, source.id, event_id, roles, limit=1)
        if not people:
            continue
        person = people[0]
        route = settlement_connection_weight(world, source, target, "trade")
        route *= 1.0 + min(source.cultural_influence / 10.0, 0.5)
        candidates.append((
            -route,
            _stable_tiebreak(world.seed, event_id, person.id),
            source.id,
            person,
        ))
    candidates.sort(key=lambda item: item[:3])
    return [candidates[0][3]] if candidates else []


def _person_effects(people, target_id: str, event, movement_type: str,
                    mobility_status: str, travel_role: str,
                    minimum_stay: int | None, maximum_stay: int | None,
                    carried_ids: list[str],
                    *, distribute_carried: bool = False) -> list[MovePerson]:
    if not target_id or not people:
        return []
    effects = []
    for index, person in enumerate(people):
        stay_until = None
        if minimum_stay is not None and maximum_stay is not None:
            span = maximum_stay - minimum_stay + 1
            duration = minimum_stay + (
                _stable_tiebreak(event.year, event.id, person.id) % span)
            stay_until = event.year + duration
        if distribute_carried:
            carried = [
                evidence_id for offset, evidence_id in enumerate(carried_ids)
                if offset % len(people) == index
            ]
        else:
            carried = list(carried_ids) if index == 0 else []
        effects.append(MovePerson(
            person_id=person.id,
            target_settlement_id=target_id,
            movement_type=movement_type,
            event_id=event.id,
            movement_year=event.year,
            mobility_status=mobility_status,
            travel_role=travel_role,
            stay_until_year=stay_until,
            carried_evidence_ids=carried,
        ))
    return effects


def _carried_evidence_by_type(event) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for transfer in event.details.get("object_transfers", []):
        transfer_type = transfer.get("transfer_type", "")
        evidence_id = transfer.get("evidence_id", "")
        if transfer_type and evidence_id:
            result.setdefault(transfer_type, []).append(evidence_id)
    return result


def _destroyed_by_event(event) -> bool:
    return any(
        effect.get("effect_type") == "destroy_settlement"
        for effect in event.effects
    )
