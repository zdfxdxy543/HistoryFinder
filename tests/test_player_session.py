"""Playable local-map session tests and truth-boundary checks."""

import json
from collections import Counter, deque

import pytest

from game.player_session import PlayerActionError, PlayerSession
from game.local_map import (
    TILE_BRIDGE,
    TILE_FARMLAND,
    TILE_FOREST,
    TILE_MARSH,
    TILE_ROCK,
    TILE_SAND,
    TILE_TUNDRA,
    LocalMapBuilder,
    PLACEMENT_PROFILES,
    build_evidence_targets,
)
from game.local_time import BREAK_PLACE_TYPES
from simulation.effects import DamageBuilding, ModifyInfrastructure
from simulation.world import World


FORBIDDEN_KEYS = {
    "event_id",
    "source_event_ids",
    "event_ids",
    "event_title",
    "event_details",
    "participants",
    "outcome_type",
    "created_year",
    "mobility_status",
    "travel_role",
    "origin_location_id",
    "stay_until_year",
    "claimant_ids",
    "owner_id",
    "location_history",
    "trigger_factors",
}


@pytest.fixture
def player_session():
    world = World(seed=415)
    world.generate(years=0)
    return PlayerSession(world)


def _all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def _reachable_positions(local_map):
    width = local_map["width"]
    height = local_map["height"]
    blocking = set(local_map["blocking_tiles"])
    blocking_entities = {
        (item["x"], item["y"])
        for item in local_map["entities"]
        if item["kind"] in {"container", "evidence"}
        and item.get("blocks_movement", True)
    }
    start = (local_map["player_start"]["x"], local_map["player_start"]["y"])
    queue = deque([start])
    reached = {start}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            neighbor = (x + dx, y + dy)
            nx, ny = neighbor
            if neighbor in reached or not (0 <= nx < width and 0 <= ny < height):
                continue
            if (local_map["tiles"][ny * width + nx] in blocking
                    or neighbor in blocking_entities):
                continue
            reached.add(neighbor)
            queue.append(neighbor)
    return reached


def _stand_next_to(session, entity):
    reached = _reachable_positions(session.local_map)
    candidates = sorted(
        position for position in reached
        if abs(position[0] - entity["x"]) + abs(position[1] - entity["y"]) <= 1
        and position != (entity["x"], entity["y"])
    )
    assert candidates, f"no reachable neighbor for {entity['id']}"
    session.local_time.player = {"x": candidates[0][0], "y": candidates[0][1]}


def _discover_all_physical_evidence(session):
    for container in (
            item for item in session.local_map["entities"]
            if item["kind"] == "container"):
        _stand_next_to(session, container)
        session.search_container(container["id"])
    for evidence in (
            item for item in session.local_map["entities"]
            if item["kind"] == "evidence"):
        _stand_next_to(session, evidence)
        session.examine(evidence["id"])
    return list(session.local_map["discovered_evidence"])


def _protected_door_cells(building):
    left, top, right, bottom = building["bounds"]
    door_x, door_y = building["door"]["x"], building["door"]["y"]
    if door_y == top:
        inward, sideways = (0, 1), (1, 0)
    elif door_y == bottom:
        inward, sideways = (0, -1), (1, 0)
    elif door_x == left:
        inward, sideways = (1, 0), (0, 1)
    else:
        inward, sideways = (-1, 0), (0, 1)
    protected = {
        (door_x, door_y),
        (door_x - inward[0], door_y - inward[1]),
    }
    for depth in range(1, 4):
        center = (door_x + inward[0] * depth, door_y + inward[1] * depth)
        protected.add(center)
        if depth <= 2:
            protected.add((center[0] + sideways[0], center[1] + sideways[1]))
            protected.add((center[0] - sideways[0], center[1] - sideways[1]))
    return protected


def test_bootstrap_is_player_safe_and_has_walkable_entities(player_session):
    payload = player_session.bootstrap()
    local_map = payload["local_map"]
    blocking = set(local_map["blocking_tiles"])
    positions = set()

    assert payload["mode"] == "player_safe"
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(payload))
    assert local_map["width"] * local_map["height"] == len(local_map["tiles"])
    assert local_map["entities"]
    assert local_map["discovered_evidence"] == []
    assert any(item["kind"] == "container" for item in local_map["entities"])
    assert any(
        item["kind"] == "evidence"
        and item["placement_kind"] == "structural"
        for item in local_map["entities"])
    for entity in local_map["entities"]:
        position = (entity["x"], entity["y"])
        assert position not in positions
        positions.add(position)
        tile = local_map["tiles"][
            entity["y"] * local_map["width"] + entity["x"]]
        if entity["kind"] in {"informant", "resident"}:
            assert tile not in blocking


def test_local_map_contains_living_buildings_and_ordinary_residents(
        player_session):
    local_map = player_session.local_map
    building_types = {
        item["building_type"] for item in local_map["buildings"]}
    residents = [
        item for item in local_map["entities"]
        if item["kind"] == "resident"]
    informant_ids = {
        item["id"] for item in local_map["entities"]
        if item["kind"] == "informant"}

    assert {"home", "inn", "bakery", "granary", "well"} <= building_types
    assert len(residents) >= 6
    assert all(item["role_name"] for item in residents)
    assert all(item["description_cn"] for item in residents)
    assert len({item["dialogue_cn"] for item in residents}) == len(residents)
    assert informant_ids.isdisjoint(item["id"] for item in residents)


def test_development_events_create_real_local_map_buildings():
    world = World(seed=451)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.size = "city"
    settlement.population = max(settlement.population, 2200)
    settlement.peak_population = max(settlement.peak_population, 2200)

    for infrastructure_type in (
            "temple", "library", "market", "fortification", "aqueduct",
            "palace"):
        result = ModifyInfrastructure(
            settlement.id, infrastructure_type, 1.0,
            reason="test_construction").apply(world)
        assert result.success

    local_map = LocalMapBuilder().build(world, settlement)
    projected = {
        item["infrastructure_type"]: item
        for item in local_map["buildings"]
        if item["infrastructure_type"]
    }

    expected_types = {
        "temple", "library", "market", "fortification", "aqueduct",
        "palace",
    }
    assert expected_types <= set(projected)
    assert projected["library"]["building_type"] == "library"
    assert projected["library"]["name"] == "图书馆"
    assert projected["market"]["building_type"] == "great_market"
    assert all(projected[item_type]["condition"] == "intact"
               for item_type in expected_types)
    assert all(projected[item_type]["infrastructure_level"] == 1.0
               for item_type in expected_types)
    assert "market" in {
        item["building_type"] for item in local_map["buildings"]}


def test_destroyed_infrastructure_remains_as_ruin_on_local_map():
    world = World(seed=452)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.size = "town"
    settlement.population = max(settlement.population, 800)
    settlement.peak_population = max(settlement.peak_population, 800)
    ModifyInfrastructure(
        settlement.id, "library", 1.0,
        reason="test_construction").apply(world)
    DamageBuilding(
        settlement.id, "library", 1.0,
        reason="test_destruction").apply(world)

    local_map = LocalMapBuilder().build(world, settlement)
    library = next(
        item for item in local_map["buildings"]
        if item["infrastructure_type"] == "library")

    assert settlement.infrastructure["library"] == 0.0
    assert library["building_type"] == "library"
    assert library["condition"] == "ruined"
    assert library["infrastructure_level"] == 0.0
    assert library["name"] == "废弃的图书馆"


def test_search_discovers_every_surviving_physical_item_at_location(
        player_session):
    first_evidence_id = next(
        item.id for item in player_session.world.evidence.values()
        if item.location_id == player_session.current_location_id
        and item.state != "destroyed"
        and item.evidence_type != "oral")
    with pytest.raises(PlayerActionError, match="找不到"):
        player_session.examine(first_evidence_id)

    found = _discover_all_physical_evidence(player_session)
    expected_ids = {
        item.id for item in player_session.world.evidence.values()
        if item.location_id == player_session.current_location_id
        and item.state != "destroyed"
        and item.evidence_type != "oral"
    }

    assert {item["id"] for item in found} == expected_ids
    assert {
        item["id"] for item in player_session.local_map["discovered_evidence"]
    } == expected_ids
    assert player_session.knowledge.discovered_evidence_ids == expected_ids
    assert all(item["searched"] for item in player_session.local_map["entities"]
               if item["kind"] == "container")
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(found))


def test_buried_items_are_found_but_destroyed_items_are_not():
    world = World(seed=421)
    world.generate(years=0)
    location_id = next(iter(world.settlements))
    physical = [
        item for item in world.evidence.values()
        if item.location_id == location_id and item.evidence_type != "oral"
    ]
    assert len(physical) >= 2
    physical[0].state = "buried"
    physical[1].state = "destroyed"
    session = PlayerSession(world, settlement_id=location_id)

    found = _discover_all_physical_evidence(session)
    found_ids = {item["id"] for item in found}

    assert physical[0].id in found_ids
    assert physical[1].id not in found_ids
    assert physical[1].container_id not in {
        item["id"] for item in session.local_map["entities"]
        if item["kind"] == "container"
    } or any(
        item.container_id == physical[1].container_id
        and item.id != physical[1].id
        and item.state != "destroyed"
        and item.evidence_type != "oral"
        for item in world.evidence.values()
    )
    assert physical[1].id not in session.knowledge.discovered_evidence_ids


def test_all_world_locations_expose_targets_for_surviving_physical_evidence():
    world = World(seed=422)
    world.generate(years=30)
    builder = LocalMapBuilder()

    for settlement in world.settlements.values():
        local_map = builder.build(world, settlement)
        expected_evidence_ids = {
            item.id for item in world.evidence.values()
            if item.location_id == settlement.id
            and item.state != "destroyed"
            and item.evidence_type != "oral"
        }
        targets = build_evidence_targets(
            world.evidence.values(), world.storage_sites, settlement.id)
        for target in targets:
            capacity = PLACEMENT_PROFILES[target["placement_kind"]][2]
            assert len(target["evidence_ids"]) <= capacity
        covered_evidence_ids = {
            evidence_id for target in targets
            for evidence_id in target["evidence_ids"]
        }
        actual_target_ids = {
            item["id"] for item in local_map["entities"]
            if item["kind"] in {"container", "evidence"}
        }
        assert covered_evidence_ids == expected_evidence_ids
        assert actual_target_ids == {item["id"] for item in targets}
        reached = _reachable_positions(local_map)
        protected = set().union(*(
            _protected_door_cells(building)
            for building in local_map["buildings"]
        ))
        for target in (
                item for item in local_map["entities"]
                if item["kind"] in {"container", "evidence"}):
            assert (target["x"], target["y"]) not in protected
            assert any(
                (target["x"] + dx, target["y"] + dy) in reached
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1))
            )


def test_documents_use_fixtures_and_in_situ_evidence_stays_on_map():
    world = World(seed=423)
    world.generate(years=30)
    for settlement in world.settlements.values():
        targets = build_evidence_targets(
            world.evidence.values(), world.storage_sites, settlement.id)
        target_by_evidence = {
            evidence_id: target for target in targets
            for evidence_id in target["evidence_ids"]
        }
        for evidence in world.evidence.values():
            if (evidence.location_id != settlement.id
                    or evidence.state == "destroyed"
                    or evidence.evidence_type == "oral"):
                continue
            target = target_by_evidence[evidence.id]
            if evidence.state == "buried":
                assert target["placement_kind"] == "excavation"
            elif evidence.evidence_type == "structure":
                assert target["kind"] == "evidence"
                assert target["placement_kind"] == "structural"
            elif evidence.evidence_type == "environmental":
                assert target["kind"] == "evidence"
                assert target["placement_kind"] == "stratigraphic"
            elif evidence.evidence_type == "document" and evidence.material == "stone":
                assert target["placement_kind"] == "stone_display"
            elif (evidence.evidence_type == "document"
                  and world.storage_sites[evidence.container_id].site_type
                  != "field_site"):
                assert target["kind"] == "container"
                assert target["placement_kind"] in {
                    "bookshelf", "archive_cabinet", "scroll_chest",
                    "ledger_shelf", "document_chest",
                }


def test_library_and_temple_containers_fall_back_to_archive_building():
    world = World(seed=400)
    world.generate(years=30)
    settlement = next(
        item for item in world.settlements.values()
        if {"library_collection", "temple_repository"} <= {
            site.site_type for site in world.storage_sites.values()
            if site.settlement_id == item.id and site.alive
        }
        and "library" not in item.infrastructure
        and "temple" not in item.infrastructure
    )
    local_map = LocalMapBuilder().build(world, settlement)
    archive = next(
        item for item in local_map["buildings"]
        if item["building_type"] == "archive")
    assert not any(
        item["building_type"] in {"library", "temple"}
        for item in local_map["buildings"])

    fallback_containers = [
        item for item in local_map["entities"]
        if item["kind"] == "container"
        and item["storage_site_id"] in world.storage_sites
        and world.storage_sites[item["storage_site_id"]].site_type
        in {"library_collection", "temple_repository"}
    ]
    assert {item["placement_kind"] for item in fallback_containers} >= {
        "bookshelf", "scroll_chest"}
    left, top, right, bottom = archive["bounds"]
    assert all(
        left < item["x"] < right and top < item["y"] < bottom
        for item in fallback_containers)


def test_talking_to_resident_is_safe_and_does_not_create_claims(player_session):
    resident = next(
        item for item in player_session.local_map["entities"]
        if item["kind"] == "resident")
    claims_before = player_session.journal_payload()["counts"]["claims"]

    result = player_session.talk(resident["id"])

    assert result["action"] == "talk"
    assert result["resident"]["role_name"]
    assert result["resident"]["portrait_visual"]
    assert result["resident"]["portrait_visual"] == resident["portrait_visual"]
    assert result["dialogue_cn"]
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(result))
    assert player_session.journal_payload()["counts"]["claims"] == claims_before


def test_read_requires_examination(player_session):
    _discover_all_physical_evidence(player_session)
    document_id = next(
        item["id"] for item in player_session.local_map["discovered_evidence"]
        if item["kind"] == "evidence" and item["subtype"] == "document")

    with pytest.raises(PlayerActionError, match="先检查"):
        player_session.read(document_id)


def test_public_inscription_is_visible_and_readable_without_examination(
        player_session):
    inscription = next(
        item for item in player_session.local_map["entities"]
        if item["kind"] == "evidence" and item.get("quick_read"))
    assert inscription["can_read"] is True
    assert "一眼可以看出" in inscription["description_cn"]
    assert "原话" in inscription["description_cn"]
    assert inscription["id"] not in \
        player_session.knowledge.examined_evidence_ids

    _stand_next_to(player_session, inscription)
    result = player_session.read(inscription["id"])

    assert result["reading"]["status"] == "readable"
    assert result["elapsed_minutes"] == 5
    assert inscription["id"] in \
        player_session.knowledge.discovered_evidence_ids
    assert inscription["id"] not in \
        player_session.knowledge.examined_evidence_ids
    assert result["local_map"]["discovered_evidence"]
    assert result["learned_claims"]
    assert all("声称" in item["statement_cn"]
               for item in result["learned_claims"])


def test_examine_read_and_consult_update_safe_journal(player_session):
    _discover_all_physical_evidence(player_session)
    document_id = next(
        item["id"] for item in player_session.local_map["discovered_evidence"]
        if item["kind"] == "evidence" and item["subtype"] == "document")
    informant_id = next(
        item["id"] for item in player_session.local_map["entities"]
        if item["kind"] == "informant")

    examined = player_session.examine(document_id)
    read = player_session.read(document_id)
    consulted = player_session.consult(document_id, informant_id)

    assert examined["observations"]
    assert examined["item_visual"]["kind"] in {
        "codex", "scroll", "sheet", "tablet"}
    assert examined["item_visual"]["material"] in {
        "parchment", "stone", "metal", "wood", "cloth"}
    assert 0.0 <= examined["item_visual"]["condition"] <= 1.0
    assert examined["item_visual"] == player_session.examine(
        document_id)["item_visual"]
    assert read["reading"]["evidence_id"] == document_id
    assert consulted["consultation"]["consultant_id"] == informant_id
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(examined))
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(read))
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(consulted))
    assert player_session.journal_payload()["counts"]["examined"] >= 1


def test_compare_two_examined_map_objects(player_session):
    _discover_all_physical_evidence(player_session)
    evidence_ids = [
        item["id"] for item in player_session.local_map["discovered_evidence"]
        if item["kind"] == "evidence"][:2]
    assert len(evidence_ids) == 2
    for evidence_id in evidence_ids:
        player_session.examine(evidence_id)

    result = player_session.compare(*evidence_ids)

    assert result["comparison"]["evidence_ids"]
    assert result["comparison"]["limitations_cn"]
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(result))


def test_local_map_is_deterministic():
    first_world = World(seed=416)
    second_world = World(seed=416)
    first_world.generate(years=0)
    second_world.generate(years=0)

    assert PlayerSession(first_world).local_map == PlayerSession(
        second_world).local_map


def test_map_sizes_and_geographic_layouts_are_data_driven():
    world = World(seed=42)
    world.generate(years=0)
    builder = LocalMapBuilder()
    settlements = list(world.settlements.values())
    profiles = [builder._profile(world, item) for item in settlements]
    layouts = {item.layout_type for item in profiles}
    landscapes = {item.landscape_type for item in profiles}

    assert len(layouts) >= 3
    assert "river" in layouts
    assert layouts & {"harbor", "woodland", "terrace", "oasis", "frontier"}
    assert len(landscapes) >= 3

    maps = [builder.build(world, item) for item in settlements]
    natural_tiles = {
        TILE_SAND, TILE_FOREST, TILE_ROCK,
        TILE_FARMLAND, TILE_TUNDRA, TILE_MARSH,
    }
    signatures = {
        tuple(Counter(local_map["tiles"])[tile] for tile in natural_tiles)
        for local_map in maps
    }
    farmland_centers = []
    for local_map in maps:
        farmland = [
            index for index, tile in enumerate(local_map["tiles"])
            if tile == TILE_FARMLAND
        ]
        if farmland:
            farmland_centers.append(sum(
                index // local_map["width"] for index in farmland
            ) / len(farmland) / local_map["height"])

    assert len(signatures) >= 6
    assert min(farmland_centers) < 0.40
    assert max(farmland_centers) > 0.60

    river_maps = [
        local_map for local_map in maps
        if local_map["profile"]["layout_type"] == "river"
    ]
    assert river_maps
    for local_map in river_maps:
        bridges = [
            (index % local_map["width"], index // local_map["width"])
            for index, tile in enumerate(local_map["tiles"])
            if tile == TILE_BRIDGE
        ]
        assert len(bridges) >= 6
        if local_map["profile"]["water_axis"] == "vertical":
            row_counts = Counter(y for _, y in bridges)
            assert max(row_counts.values()) >= 3
        elif local_map["profile"]["water_axis"] == "horizontal":
            column_counts = Counter(x for x, _ in bridges)
            assert max(column_counts.values()) >= 3
        else:
            assert len({x for x, _ in bridges}) >= 3
            assert len({y for _, y in bridges}) >= 3

    settlement = settlements[0]
    dimensions = []
    for size, population, peak in (
            ("village", 100, 100),
            ("village", 240, 240),
            ("town", 600, 600),
            ("city", 2200, 2200)):
        settlement.size = size
        settlement.population = population
        settlement.peak_population = peak
        profile = builder._profile(world, settlement)
        dimensions.append((profile.width, profile.height))

    assert dimensions == [(80, 56), (96, 64), (120, 80), (144, 96)]


def test_entities_buildings_and_npc_destinations_are_reachable(player_session):
    local_map = player_session.local_map
    reached = _reachable_positions(local_map)
    required = {
        "hall", "market", "archive", "workshop", "inn",
        "granary", "bakery", "well", "home",
    }

    assert required <= {
        item["building_type"] for item in local_map["buildings"]}
    for entity in local_map["entities"]:
        if entity["kind"] in {"informant", "resident"}:
            assert (entity["x"], entity["y"]) in reached
        else:
            assert any(
                (entity["x"] + dx, entity["y"] + dy) in reached
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)))
    for building in local_map["buildings"]:
        assert (building["door"]["x"], building["door"]["y"]) in reached
    for npc in player_session.local_time._npcs.values():
        assert npc["home"] in reached
        assert npc["work"] in reached
        assert npc["midday"] in reached


def test_blocking_evidence_target_cannot_be_walked_through(player_session):
    local_map = player_session.local_map
    blocking_tiles = set(local_map["blocking_tiles"])
    target = next(
        item for item in local_map["entities"]
        if item["kind"] in {"container", "evidence"}
        and item["blocks_movement"]
        and local_map["tiles"][
            item["y"] * local_map["width"] + item["x"]
        ] not in blocking_tiles
    )
    _stand_next_to(player_session, target)
    before = player_session.local_time.snapshot()
    dx = target["x"] - before["player"]["x"]
    dy = target["y"] - before["player"]["y"]

    result = player_session.move(dx, dy)

    assert result["moved"] is False
    assert result["runtime"]["player"] == before["player"]
    assert result["runtime"]["turn"] == before["turn"]


def test_player_steps_advance_clock_and_start_npc_commutes():
    world = World(seed=417)
    world.generate(years=0)
    session = PlayerSession(world)
    before = session.local_time.snapshot()

    result = session.move(-1, 0)

    assert result["moved"] is True
    assert result["runtime"]["time_label"] == "06:56"
    assert result["runtime"]["minute_of_day"] == before["minute_of_day"] + 1
    assert result["runtime"]["turn"] == before["turn"] + 1


def test_npc_homes_breaks_and_departures_are_distributed():
    world = World(seed=415)
    world.generate(years=0)
    session = PlayerSession(world)
    simulation = session.local_time

    def building_at(position, building_types):
        for building in session.local_map["buildings"]:
            if building["building_type"] not in building_types:
                continue
            left, top, right, bottom = building["bounds"]
            if left < position[0] < right and top < position[1] < bottom:
                return building["id"]
        return "outdoor"

    homes = {
        building_at(npc["home"], {"home"})
        for npc in simulation._npcs.values()
    }
    break_places = {
        building_at(npc["midday"], set(BREAK_PLACE_TYPES))
        for npc in simulation._npcs.values()
    }
    doors = {
        (item["door"]["x"], item["door"]["y"])
        for item in session.local_map["buildings"]
    }
    offsets = {
        npc["schedule_offset"] for npc in simulation._npcs.values()}

    assert len(homes) >= 5
    assert len(break_places) >= 4
    assert len(offsets) >= 5
    assert min(offsets) < 0 < max(offsets)
    assert all(
        npc[target] not in doors
        for npc in simulation._npcs.values()
        for target in ("home", "work", "midday")
    )


@pytest.mark.parametrize("seed", [415, 421, 422])
def test_staggered_commute_reaches_work_without_door_deadlock(seed):
    world = World(seed=seed)
    world.generate(years=0)
    session = PlayerSession(world)

    runtime = session.local_time.advance(245)

    assert runtime["time_label"] == "11:00"
    assert all(
        (npc["x"], npc["y"]) == npc["work"]
        for npc in session.local_time._npcs.values()
    )
    positions = {
        (npc["x"], npc["y"])
        for npc in session.local_time._npcs.values()
    }
    assert len(positions) == len(session.local_time._npcs)


def test_wait_and_investigation_actions_have_explicit_duration():
    world = World(seed=418)
    world.generate(years=0)
    session = PlayerSession(world)
    waited = session.wait(10)
    _discover_all_physical_evidence(session)
    evidence_id = next(
        item["id"] for item in session.local_map["discovered_evidence"]
        if item["kind"] == "evidence")
    turn_before_examine = session.local_time.turn
    examined = session.examine(evidence_id)

    assert waited["runtime"]["turn"] == 10
    assert examined["elapsed_minutes"] == 15
    assert examined["runtime"]["turn"] == turn_before_examine + 15
    positions = {
        (item["x"], item["y"]) for item in examined["runtime"]["npcs"]}
    assert len(positions) == len(examined["runtime"]["npcs"])


def test_first_cheat_unlocks_optional_full_map_vision():
    world = World(seed=421)
    world.generate(years=0)
    session = PlayerSession(world)
    tile_count = session.local_map["width"] * session.local_map["height"]
    normal_visible = len(session.local_time.snapshot()["visible_tiles"])

    unlocked = session.enter_cheat_code("hf-vision")

    assert unlocked["cheats"]["full_map_vision"] == {
        "unlocked": True,
        "enabled": False,
    }
    assert len(unlocked["runtime"]["visible_tiles"]) == normal_visible

    enabled = session.set_cheat("full_map_vision", True)

    assert enabled["runtime"]["full_map_vision"] is True
    assert len(enabled["runtime"]["visible_tiles"]) == tile_count
    assert len(enabled["runtime"]["explored_tiles"]) < tile_count

    disabled = session.set_cheat("full_map_vision", False)

    assert disabled["runtime"]["full_map_vision"] is False
    assert len(disabled["runtime"]["visible_tiles"]) < tile_count


def test_full_map_vision_requires_the_cheat_code_and_survives_travel():
    world = World(seed=422)
    world.generate(years=0)
    session = PlayerSession(world)

    with pytest.raises(PlayerActionError, match="尚未解锁"):
        session.set_cheat("full_map_vision", True)
    with pytest.raises(PlayerActionError, match="作弊码无效"):
        session.enter_cheat_code("wrong-code")

    session.enter_cheat_code("HF-VISION")
    session.set_cheat("full_map_vision", True)
    destination_id = next(
        item.id for item in world.settlements.values()
        if item.id != session.current_location_id)

    traveled = session.travel(destination_id)
    runtime = traveled["location"]["runtime"]

    assert runtime["full_map_vision"] is True
    assert len(runtime["visible_tiles"]) == (
        session.local_map["width"] * session.local_map["height"])


def test_world_map_travel_loads_and_reuses_local_maps():
    world = World(seed=419)
    world.generate(years=0)
    session = PlayerSession(world)
    assert json.dumps(session.bootstrap(), ensure_ascii=False)
    origin_id = session.current_location_id
    origin_map = session.local_map
    destination_id = next(
        item.id for item in world.settlements.values()
        if item.id != origin_id)

    traveled = session.travel(destination_id)

    assert traveled["action"] == "travel"
    assert traveled["elapsed_minutes"] >= 60
    assert traveled["location"]["settlement"]["id"] == destination_id
    assert traveled["world_map"]["current_location_id"] == destination_id
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(traveled))

    session.travel(origin_id)
    assert session.local_map is origin_map


def test_world_map_travel_restores_explored_tiles_for_each_local_map():
    world = World(seed=419)
    world.generate(years=0)
    session = PlayerSession(world)
    session.bootstrap()
    origin_id = session.current_location_id
    destination_id = next(
        item.id for item in world.settlements.values()
        if item.id != origin_id)
    remembered = set(session.local_time._explored_cells)
    assert remembered

    session.travel(destination_id)
    session.travel(origin_id)

    assert remembered <= session.local_time._explored_cells


def test_world_map_exposes_public_territories_without_polity_ids():
    world = World(seed=419)
    world.generate(years=0)
    world_map = PlayerSession(world).bootstrap()["world_map"]
    territory = world_map["territory"]

    assert len(territory["owners"]) == world.geography.height
    assert len(territory["owners"][0]) == world.geography.width
    assert territory["polities"]
    assert all(set(polity) == {"code", "name"}
               for polity in territory["polities"])
    valid_codes = {polity["code"] for polity in territory["polities"]}
    valid_codes.add(territory["unclaimed_code"])
    assert all(code in valid_codes
               for row in territory["owners"] for code in row)
    assert "polity_id" not in set(_all_keys(world_map))
    assert "controller_polity_id" not in set(_all_keys(world_map))


def test_world_map_exposes_named_geographic_features():
    world = World(seed=42)
    world.generate(years=0)
    world_map = PlayerSession(world).bootstrap()["world_map"]
    features = world_map["geographic_features"]

    assert features
    assert {"river", "mountain", "plains"} <= {
        item["feature_type"] for item in features}
    assert len({item["name"] for item in features}) == len(features)
    assert all(0 <= item["x"] < world_map["width"] for item in features)
    assert all(0 <= item["y"] < world_map["height"] for item in features)
    assert all(item["min_zoom"] >= 1.0 for item in features)


def test_destroyed_settlement_loads_as_walkable_ruin_with_search_sites():
    world = World(seed=420)
    world.generate(years=0)
    session = PlayerSession(world)
    ruin = next(
        item for item in world.settlements.values()
        if item.id != session.current_location_id)
    ruin.alive = False
    ruin.destroyed_year = world.current_year

    ruin_session = PlayerSession(world, ruin.id)
    local_map = ruin_session.local_map
    blocking = set(local_map["blocking_tiles"])

    assert local_map["site_type"] == "ruin"
    survivors = [
        item for item in local_map["entities"]
        if item["kind"] == "resident"]
    assert survivors
    assert all(item["state"] == "ruin_survivor" for item in survivors)
    assert all(item["dialogue_cn"] for item in survivors)
    reached = _reachable_positions(local_map)
    for target in (
            item for item in local_map["entities"]
            if item["kind"] in {"container", "evidence"}):
        assert any(
            (target["x"] + dx, target["y"] + dy) in reached
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)))
