"""Persistent storage locations for physical evidence."""

import copy
import random

from simulation.effects import DamageBuilding, DestroySettlement, EffectResolver
from simulation.evidence import Evidence, tick_natural_decay
from simulation.events import HistoricalEvent
from simulation.storage import StorageManager, StorageSite
from simulation.world import World
from viewer.data import build_world_payload


def _world(years=8):
    world = World(seed=42)
    world.generate(years=years)
    return world


def test_generated_evidence_has_valid_persistent_location():
    world = _world()

    assert world.storage_sites
    for evidence in world.evidence.values():
        assert evidence.container_id in world.storage_sites
        assert evidence.holder_type == "site"
        assert evidence.holder_id == evidence.container_id
        assert evidence.storage_position
        assert evidence.location_history
        assert evidence.location_history[-1]["to_container_id"] == evidence.container_id


def test_documents_are_sorted_into_domain_specific_collections():
    world = _world(0)
    settlement = next(iter(world.settlements.values()))
    world._add_event_with_evidence(HistoricalEvent(
        id="event_storage_literature",
        year=1,
        event_type="literary_work",
        title="A chronicle",
        severity=0.2,
        primary_location=settlement.id,
        participants=[settlement.id],
        details={
            "genre": "chronicle",
            "work_title": "Storage Chronicle",
            "author_name": "Test Author",
        },
    ))
    world._add_event_with_evidence(HistoricalEvent(
        id="event_storage_theory",
        year=2,
        event_type="theoretical_work",
        title="A treatise",
        severity=0.2,
        primary_location=settlement.id,
        participants=[settlement.id],
        details={
            "theory_field": "mechanics",
            "theory_field_name": "力学",
            "work_title": "Storage Treatise",
            "author_name": "Test Scholar",
        },
    ))
    expected = {
        "founding_charter": "administrative_archive",
        "literary_manuscript": "library_collection",
        "theoretical_treatise": "library_collection",
        "religious_text": "temple_repository",
        "trade_ledger": "merchant_archive",
    }

    found = set()
    for evidence in world.evidence.values():
        subtype = evidence.subtype.removesuffix("_copy")
        if subtype not in expected or evidence.is_copy_of:
            continue
        site = world.storage_sites[evidence.container_id]
        assert site.site_type == expected[subtype]
        found.add(subtype)
    assert {"founding_charter", "literary_manuscript", "theoretical_treatise"} <= found


def test_document_copy_is_stored_separately_from_original():
    world = _world()
    copy_item = next(
        item for item in world.evidence.values()
        if item.is_copy_of and item.evidence_type == "document")
    original = world.evidence[copy_item.is_copy_of]

    assert copy_item.container_id != original.container_id
    assert copy_item.is_copy_of == original.id


def test_move_evidence_updates_location_and_custody_history():
    world = _world(0)
    evidence = next(iter(world.evidence.values()))
    target = next(
        site for site in world.storage_sites.values()
        if site.settlement_id == evidence.location_id
        and site.id != evidence.container_id)
    history_length = len(evidence.location_history)

    assert world.move_evidence(
        evidence.id, target.id, year=3, reason="catalogue_transfer")
    assert evidence.container_id == target.id
    assert evidence.holder_id == target.id
    assert evidence.location_id == target.settlement_id
    assert len(evidence.location_history) == history_length + 1
    assert evidence.location_history[-1]["reason"] == "catalogue_transfer"


def test_archive_environment_reduces_decay():
    base = Evidence(
        id="evd_test", event_id="event_test", evidence_type="document",
        subtype="test", location_type="settlement", location_id="stl_test",
        created_year=0, material="parchment", max_durability=80.0,
        current_durability=80.0,
    )
    protected = copy.deepcopy(base)
    exposed = copy.deepcopy(base)
    site = StorageSite(
        id="site_test", settlement_id="stl_test",
        site_type="library_collection", name="Test Library",
        preservation_modifier=0.55,
    )

    tick_natural_decay(protected, site.effective_preservation_modifier,
                       random.Random(9))
    tick_natural_decay(exposed, 1.45, random.Random(9))
    assert protected.current_durability > exposed.current_durability


def test_destroy_settlement_moves_survivors_and_can_be_reversed():
    world = _world(0)
    settlement = next(iter(world.settlements.values()))
    before = {
        item.id: (item.container_id, list(item.location_history))
        for item in world.evidence.values()
        if item.location_id == settlement.id
    }
    resolver = EffectResolver(seed=202)

    ids = resolver.apply_effects([
        DestroySettlement(settlement.id, cause="earthquake", reason="test"),
    ], world)
    survivors = [item for item in world.evidence.values()
                 if item.location_id == settlement.id and item.state != "destroyed"]
    assert survivors
    assert all(world.storage_sites[item.container_id].site_type == "field_site"
               for item in survivors)

    assert resolver.reverse_effect(ids[0], world)
    assert settlement.alive
    for evidence_id, (container_id, history) in before.items():
        assert world.evidence[evidence_id].container_id == container_id
        assert world.evidence[evidence_id].location_history == history


def test_destroyed_library_evacuates_collection_and_rollback_restores_it():
    world = _world(0)
    library = next(site for site in world.storage_sites.values()
                   if site.site_type == "library_collection")
    stored_before = [item.id for item in world.evidence.values()
                     if item.container_id == library.id]
    resolver = EffectResolver(seed=203)

    ids = resolver.apply_effects([
        DamageBuilding(library.settlement_id, "library", 1.0, reason="test"),
    ], world)
    assert not world.storage_sites[library.id].alive
    assert all(world.evidence[item_id].container_id != library.id
               for item_id in stored_before)

    assert resolver.reverse_effect(ids[0], world)
    assert world.storage_sites[library.id].alive
    assert all(world.evidence[item_id].container_id == library.id
               for item_id in stored_before)


def test_storage_roundtrip_and_legacy_migration():
    world = _world(3)
    restored = World.from_dict(world.to_dict())
    assert {
        site_id: site.to_dict() for site_id, site in restored.storage_sites.items()
    } == {
        site_id: site.to_dict() for site_id, site in world.storage_sites.items()
    }
    assert all(item.container_id in restored.storage_sites
               for item in restored.evidence.values())

    legacy = world.to_dict()
    legacy.pop("storage_sites")
    legacy["schema_version"] = 6
    for item in legacy["evidence"]:
        for key in ("container_id", "holder_type", "holder_id",
                    "storage_position", "location_history"):
            item.pop(key, None)
        item["schema_version"] = 5
    migrated = World.from_dict(legacy)
    assert migrated.storage_sites
    assert all(item.container_id in migrated.storage_sites
               for item in migrated.evidence.values())
    assert all(item.schema_version == 7 for item in migrated.evidence.values())


def test_viewer_payload_exposes_storage_relationships():
    world = _world(2)
    payload = build_world_payload(world)
    sites = {item["id"]: item for item in payload["storage_sites"]}

    assert payload["summary"]["storage_sites"] == len(world.storage_sites)
    for evidence in payload["evidence"]:
        assert evidence["id"] in sites[evidence["container_id"]]["evidence_ids"]
    for settlement in payload["settlements"]:
        assert all(sites[site_id]["settlement_id"] == settlement["id"]
                   for site_id in settlement["storage_site_ids"])
