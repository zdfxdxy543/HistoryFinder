"""Build JSON-safe data for the read-only world viewer."""

from __future__ import annotations

from collections import Counter, defaultdict

from config import SEA_LEVEL
from simulation.world import World


BIOME_CODES = {
    "mountain": 0,
    "highland": 1,
    "river_valley": 2,
    "forest": 3,
    "desert": 4,
    "grassland": 5,
    "tundra": 6,
    "scrubland": 7,
    "plains": 8,
    "ocean": 9,
    "lake": 10,
    "river": 11,
}


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    return value


def build_world_payload(world: World) -> dict:
    """Return a compact, relationship-rich representation of simulation truth."""
    event_records: dict[str, list[str]] = defaultdict(list)
    record_evidence: dict[str, list[str]] = defaultdict(list)
    event_evidence: dict[str, list[str]] = defaultdict(list)
    person_events: dict[str, list[str]] = defaultdict(list)

    for record in world.records.values():
        for event_id in record.source_event_ids:
            event_records[event_id].append(record.id)
    for evidence in world.evidence.values():
        event_evidence[evidence.event_id].append(evidence.id)
        if evidence.source_record_id:
            record_evidence[evidence.source_record_id].append(evidence.id)
    site_evidence: dict[str, list[str]] = defaultdict(list)
    for evidence in world.evidence.values():
        if evidence.container_id:
            site_evidence[evidence.container_id].append(evidence.id)
    for event in world.events:
        for person_id in event.person_ids:
            person_events[person_id].append(event.id)

    settlements = []
    for settlement in world.settlements.values():
        item = settlement.to_dict()
        item["event_ids"] = list(
            world.event_history_by_settlement.get(settlement.id, []))
        item["record_ids"] = sorted({
            record_id
            for event_id in item["event_ids"]
            for record_id in event_records.get(event_id, [])
        })
        item["evidence_ids"] = sorted(
            evidence.id for evidence in world.evidence.values()
            if evidence.location_id == settlement.id)
        item["storage_site_ids"] = sorted(
            site.id for site in world.storage_sites.values()
            if site.settlement_id == settlement.id)
        settlements.append(item)

    events = []
    for event in world.events:
        item = event.to_dict()
        item["record_ids"] = event_records.get(event.id, [])
        item["evidence_ids"] = event_evidence.get(event.id, [])
        events.append(item)

    records = []
    for record in world.records.values():
        item = record.to_dict()
        item["evidence_ids"] = record_evidence.get(record.id, [])
        records.append(item)

    evidence = []
    for item in world.evidence.values():
        serialized = item.to_dict()
        serialized["condition_ratio"] = (
            item.current_durability / item.max_durability
            if item.max_durability > 0 else 0.0)
        evidence.append(serialized)

    persons = []
    for person in world.persons.values():
        item = person.to_dict()
        item["event_ids"] = person_events.get(person.id, [])
        persons.append(item)

    storage_sites = []
    for site in world.storage_sites.values():
        item = site.to_dict()
        item["evidence_ids"] = sorted(site_evidence.get(site.id, []))
        item["inventory_count"] = len(item["evidence_ids"])
        storage_sites.append(item)

    event_types = Counter(event.event_type for event in world.events)
    evidence_types = Counter(item.evidence_type for item in world.evidence.values())
    record_perspectives = Counter(
        record.perspective for record in world.records.values())
    alive = sum(1 for item in world.settlements.values() if item.alive)
    causal_events = sum(1 for event in world.events if event.cause_event_ids)

    geography = world.geography
    terrain = [
        [BIOME_CODES[str(geography.biomes[y, x])]
         for x in range(geography.width)]
        for y in range(geography.height)
    ]

    payload = {
        "schema_version": 2,
        "viewer_mode": "debug_truth",
        "world": {
            "seed": world.seed,
            "name": world.name,
            "current_year": world.current_year,
            "width": geography.width,
            "height": geography.height,
        },
        "summary": {
            "settlements": len(world.settlements),
            "alive_settlements": alive,
            "ruined_settlements": len(world.settlements) - alive,
            "events": len(world.events),
            "causal_events": causal_events,
            "records": len(world.records),
            "evidence": len(world.evidence),
            "persons": len(world.persons),
            "storage_sites": len(world.storage_sites),
            "event_types": dict(sorted(event_types.items())),
            "evidence_types": dict(sorted(evidence_types.items())),
            "record_perspectives": dict(sorted(record_perspectives.items())),
        },
        "geography": {
            "biome_codes": BIOME_CODES,
            "terrain": terrain,
            "sea_level": SEA_LEVEL,
            "ocean_cells": sum(
                1 for row in terrain for code in row
                if code == BIOME_CODES["ocean"]),
            "lake_cells": sum(
                1 for row in terrain for code in row
                if code == BIOME_CODES["lake"]),
            "river_cells": sum(
                1 for row in terrain for code in row
                if code == BIOME_CODES["river"]),
        },
        "settlements": settlements,
        "events": events,
        "records": records,
        "evidence": evidence,
        "persons": persons,
        "storage_sites": storage_sites,
    }
    return _json_safe(payload)
