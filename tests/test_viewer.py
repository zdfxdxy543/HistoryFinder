"""Read-only world viewer data contract tests."""

import json
from pathlib import Path

from simulation.world import World
from viewer.data import BIOME_CODES, build_world_payload


def _small_payload():
    world = World(seed=17)
    world.generate(years=5)
    return world, build_world_payload(world)


def test_viewer_payload_is_json_serializable_and_complete():
    world, payload = _small_payload()

    encoded = json.dumps(payload, ensure_ascii=False)

    assert encoded
    assert payload["viewer_mode"] == "debug_truth"
    assert payload["summary"]["events"] == len(world.events)
    assert payload["summary"]["records"] == len(world.records)
    assert payload["summary"]["evidence"] == len(world.evidence)
    assert len(payload["geography"]["terrain"]) == world.geography.height
    assert len(payload["geography"]["terrain"][0]) == world.geography.width
    assert set(payload["geography"]["biome_codes"]) == set(BIOME_CODES)
    assert payload["geography"]["ocean_cells"] > 0
    assert payload["geography"]["lake_cells"] > 0
    assert payload["geography"]["river_cells"] > 0


def test_viewer_payload_exposes_relationship_indexes():
    world, payload = _small_payload()
    event_by_id = {event["id"]: event for event in payload["events"]}
    record_by_id = {record["id"]: record for record in payload["records"]}
    evidence_by_id = {item["id"]: item for item in payload["evidence"]}

    for record in world.records.values():
        for event_id in record.source_event_ids:
            assert record.id in event_by_id[event_id]["record_ids"]
    for evidence in world.evidence.values():
        assert evidence.id in event_by_id[evidence.event_id]["evidence_ids"]
        if evidence.source_record_id:
            assert evidence.id in record_by_id[evidence.source_record_id]["evidence_ids"]
        assert evidence_by_id[evidence.id]["condition_ratio"] >= 0.0


def test_viewer_static_assets_exist():
    static_dir = Path(__file__).parents[1] / "viewer" / "static"

    for filename in ("index.html", "styles.css", "app.js"):
        path = static_dir / filename
        assert path.is_file()
        assert path.stat().st_size > 500
