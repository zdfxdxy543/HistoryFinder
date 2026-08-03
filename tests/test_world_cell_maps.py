"""World-cell maps, border travel, and persistent trade routes."""

import json
from collections import deque
from itertools import combinations

import pytest

from game.local_map import (
    BLOCKING_TILES,
    TILE_BRIDGE,
    TILE_FORD,
    TILE_GRASS,
    TILE_ROAD,
    TILE_WATER,
    LocalMapBuilder,
    SettlementMapProfile,
    paint_watercourse,
)
from game.local_time import LocalTimeSimulation
from game.player_session import PlayerActionError, PlayerSession
from game.world_cell_map import (
    LocalMapRepository,
    WorldCellMapBuilder,
    _carve_water,
    _obscure_text_character,
    _paint_road,
    decorate_travel_groups,
    route_portals,
)
from simulation.effects import ModifyRelationship
from simulation.routes import TradeRoute, road_segment_id
from simulation.world import World


def _overland_route(world):
    for first, second in combinations(
            sorted(world.settlements.values(), key=lambda item: item.id), 2):
        route = world.ensure_trade_route(first.id, second.id)
        if route is not None:
            return first, second, route
    raise AssertionError("test world has no overland settlement pair")


def test_trade_relationship_creates_one_deterministic_route():
    first_world = World(seed=431)
    second_world = World(seed=431)
    first_world.generate(years=0)
    second_world.generate(years=0)
    first, second, _ = _overland_route(first_world)
    first_world.trade_routes.clear()
    first_world.travel_groups.clear()

    effect = ModifyRelationship(
        first.id, second.id, trade_volume_delta=40.0, reason="trade")
    result = effect.apply(first_world)
    route = next(iter(first_world.trade_routes.values()))
    mirror_first = second_world.settlements[first.id]
    mirror_second = second_world.settlements[second.id]
    mirror_effect = ModifyRelationship(
        mirror_first.id, mirror_second.id,
        trade_volume_delta=40.0, reason="trade")
    mirror_effect.apply(second_world)

    assert result.success
    assert route.path == next(iter(second_world.trade_routes.values())).path
    assert route.path[0] == (first.grid_x, first.grid_y)
    assert route.path[-1] == (second.grid_x, second.grid_y)
    assert all(
        abs(ax - bx) + abs(ay - by) == 1
        for (ax, ay), (bx, by) in zip(route.path, route.path[1:])
    )


def test_routes_round_trip_with_world_serialization():
    world = World(seed=432)
    world.generate(years=0)
    _, _, route = _overland_route(world)

    restored = World.from_dict(json.loads(json.dumps(world.to_dict())))

    assert restored.trade_routes[route.id].to_dict() == route.to_dict()
    assert {
        key: item.to_dict() for key, item in restored.road_segments.items()
    } == {
        key: item.to_dict() for key, item in world.road_segments.items()
    }
    assert restored.travel_groups == {
        key: type(group).from_dict(group.to_dict())
        for key, group in world.travel_groups.items()
    }
    assert {
        key: item.to_dict() for key, item in restored.signposts.items()
    } == {
        key: item.to_dict() for key, item in world.signposts.items()
    }


def test_caravan_advances_and_round_trips_on_its_route():
    world = World(seed=438)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    before = (group.path_index, group.direction)

    world.advance_travel_groups(180)

    assert (group.path_index, group.direction) != before
    assert group.current_cell(route) in route.path
    restored = World.from_dict(json.loads(json.dumps(world.to_dict())))
    assert restored.travel_groups[group.id].to_dict() == group.to_dict()


def test_route_wilderness_contains_signs_and_stable_camps():
    world = World(seed=439)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    wilderness_cells = route.path[1:-1]
    assert wilderness_cells
    maps = [WorldCellMapBuilder().build(world, *cell)
            for cell in wilderness_cells]
    for local_map in maps:
        decorate_travel_groups(local_map, world)

    signs = [
        item for local_map in maps for item in local_map["entities"]
        if item["kind"] == "landmark" and item["subtype"] == "signpost"
    ]
    camps = [
        item for local_map in maps for item in local_map["entities"]
        if item["kind"] == "camp"
    ]
    assert signs
    assert len(signs) == len(world.signposts)
    assert {item.world_cell for item in world.signposts.values()} <= set(
        wilderness_cells)
    assert all("约" in item["description_cn"] for item in signs)
    assert all(item["wear_level"] in {"light", "moderate", "heavy"}
               for item in signs)
    assert all(item["repair_type"] == "none" for item in signs)
    assert all(item["repair_history"] == [] for item in signs)
    assert all(item["original_boards"] == item["current_boards"]
               for item in signs)
    assert camps
    repeated = [WorldCellMapBuilder().build(world, *cell)
                for cell in wilderness_cells]
    for local_map in repeated:
        decorate_travel_groups(local_map, world)
    assert [item["entities"] for item in maps] == [
        item["entities"] for item in repeated]


def test_signpost_text_survives_settlement_rename_and_route_removal():
    world = World(seed=439)
    world.generate(years=0)
    first, second, route = _overland_route(world)
    signpost = next(iter(world.signposts.values()))
    frozen = [item.to_dict() for item in signpost.current_boards]
    cell = signpost.world_cell

    first.name = "改名后的聚落"
    second.name = "已经废弃的聚落"
    second.alive = False
    before_removal = WorldCellMapBuilder().build(world, *cell)
    world.current_year = 9
    world.remove_trade_route(route.id)
    after_removal = WorldCellMapBuilder().build(world, *cell)

    assert [item.to_dict() for item in signpost.current_boards] == frozen
    assert world.trade_routes[route.id].status == "abandoned"
    assert signpost.abandoned_year == 9
    assert any(item["id"] == signpost.id
               for item in before_removal["entities"])
    abandoned = next(item for item in after_removal["entities"]
                     if item["id"] == signpost.id)
    assert abandoned["abandoned_year"] == 9
    assert all(item["displayed_name"] not in {
        "改名后的聚落", "已经废弃的聚落"}
        for item in abandoned["current_boards"])


def test_signpost_repair_changes_only_one_board_and_round_trips():
    world = World(seed=439)
    world.generate(years=0)
    _overland_route(world)
    signpost = next(iter(world.signposts.values()))
    target = signpost.current_boards[0]
    untouched = signpost.current_boards[1].to_dict()
    repairer = next(iter(world.persons.values()))
    world.current_year = 12

    repair = world.repair_signpost(
        signpost.id, target.id, repairer.id,
        repair_type="replacement_board", error_type="illegible_distance")
    restored = World.from_dict(json.loads(json.dumps(world.to_dict())))
    restored_signpost = restored.signposts[signpost.id]

    assert repair.error_type == "illegible_distance"
    assert "？" in signpost.current_boards[0].displayed_distance
    assert signpost.current_boards[1].to_dict() == untouched
    assert restored_signpost.to_dict() == signpost.to_dict()


def test_schema_16_save_migrates_route_signposts():
    world = World(seed=439)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    legacy = world.to_dict()
    legacy["schema_version"] = 16
    legacy.pop("signposts")

    restored = World.from_dict(json.loads(json.dumps(legacy)))

    assert restored.signposts
    assert all(route.id in item.route_ids
               for item in restored.signposts.values())


def test_schema_17_save_migrates_shared_road_segments():
    world = World(seed=439)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    legacy = world.to_dict()
    legacy["schema_version"] = 17
    legacy.pop("road_segments")
    for route_data in legacy["trade_routes"]:
        route_data["schema_version"] = 1
        route_data.pop("segment_ids", None)
        route_data.pop("last_active_year", None)
        route_data.pop("closed_year", None)
        route_data.pop("closure_reason", None)

    restored = World.from_dict(json.loads(json.dumps(legacy)))

    assert len(restored.road_segments) == len(route.path) - 1
    assert len(restored.trade_routes[route.id].segment_ids) == len(
        route.path) - 1


def test_duplicate_trade_route_path_reuses_physical_road_segments():
    world = World(seed=439)
    world.generate(years=0)
    first, second, route = _overland_route(world)
    cell = route.path[1]
    before_segments = set(world.road_segments)
    before_portals = route_portals(world, *cell, 80, 56)
    duplicate = TradeRoute(
        id="route_duplicate_test",
        settlement_a_id=second.id,
        settlement_b_id=first.id,
        opened_year=world.current_year,
        path=list(reversed(route.path)),
    )
    world.trade_routes[duplicate.id] = duplicate

    world._attach_route_segments(duplicate)
    after_portals = route_portals(world, *cell, 80, 56)

    assert set(world.road_segments) == before_segments
    assert after_portals == before_portals
    assert all(duplicate.id in world.road_segments[item].route_ids
               for item in duplicate.segment_ids)


def test_shared_route_signpost_displays_each_destination_once():
    world = World(seed=439)
    world.generate(years=0)
    first, second, route = _overland_route(world)
    duplicate = TradeRoute(
        id="route_duplicate_signpost_test",
        settlement_a_id=second.id,
        settlement_b_id=first.id,
        opened_year=world.current_year,
        path=list(reversed(route.path)),
    )
    world.trade_routes[duplicate.id] = duplicate
    world._attach_route_segments(duplicate)
    world._ensure_route_signposts(duplicate)
    signpost = world.signposts[
        f"signpost_{route.path[1][0]}_{route.path[1][1]}"]

    duplicate_board = next(
        item for item in signpost.current_boards
        if item.source_route_id == duplicate.id
        and item.destination_id == first.id)
    next(item for item in signpost.original_boards
         if item.id == duplicate_board.id).displayed_distance = "99"
    duplicate_board.displayed_distance = "99"

    local_map = WorldCellMapBuilder().build(world, *signpost.world_cell)
    projected = next(
        item for item in local_map["entities"] if item["id"] == signpost.id)

    assert len(signpost.current_boards) == 4
    assert projected["dialogue_cn"].count(first.name) == 1
    assert projected["dialogue_cn"].count(second.name) == 1
    assert len(projected["current_boards"]) == 2
    first_board = next(
        item for item in projected["current_boards"]
        if item["destination_id"] == first.id)
    assert first_board["source_route_id"] == route.id


def test_inactive_trade_route_and_road_have_persistent_lifecycle():
    world = World(seed=439)
    world.generate(years=0)
    first, second, route = _overland_route(world)
    from simulation.settlement import RelationshipData
    first.relationships[second.id] = RelationshipData(
        partner_id=second.id, trade_volume=0.0)
    second.relationships[first.id] = RelationshipData(
        partner_id=first.id, trade_volume=0.0)
    route.last_active_year = 0

    world.current_year = 5
    world._tick_trade_routes(5)

    assert route.status == "abandoned"
    assert route.closed_year == 5
    assert route.id in world.trade_routes
    assert not any(item.route_id == route.id
                   for item in world.travel_groups.values())
    assert all(item.abandoned_year == 5
               for item in world.signposts.values()
               if route.id in item.route_ids)
    assert all(world.road_segments[item].status == "disused"
               for item in route.segment_ids)

    world.current_year = 13
    world._tick_trade_routes(13)
    assert all(world.road_segments[item].status == "overgrown"
               for item in route.segment_ids)
    overgrown_map = WorldCellMapBuilder().build(world, *route.path[1])
    assert any(item["subtype"] == "overgrown_road"
               for item in overgrown_map["entities"])

    world.current_year = 29
    world._tick_trade_routes(29)
    assert all(world.road_segments[item].status == "ruined"
               for item in route.segment_ids)
    assert route_portals(world, *route.path[1], 80, 56) == []
    ruined_map = WorldCellMapBuilder().build(world, *route.path[1])
    assert any(item["subtype"] == "road_remains"
               for item in ruined_map["entities"])


def test_abandoned_trade_route_reopens_on_new_trade():
    world = World(seed=439)
    world.generate(years=0)
    first, second, route = _overland_route(world)
    from simulation.settlement import RelationshipData
    first.relationships[second.id] = RelationshipData(
        partner_id=second.id, trade_volume=0.0)
    second.relationships[first.id] = RelationshipData(
        partner_id=first.id, trade_volume=0.0)
    world.current_year = 5
    route.last_active_year = 0
    world._tick_trade_routes(5)

    effect = ModifyRelationship(
        first.id, second.id, trade_volume_delta=20.0, reason="trade_resumed")
    result = effect.apply(world)

    assert result.success
    assert route.status == "active"
    assert route.closed_year is None
    assert all(world.road_segments[item].status == "active"
               for item in route.segment_ids)
    assert any(item.route_id == route.id
               for item in world.travel_groups.values())


def test_stale_trade_volume_decays_and_eventually_abandons_route():
    world = World(seed=439)
    world.generate(years=0)
    first, second, _ = _overland_route(world)
    world.remove_trade_route(
        next(iter(world.trade_routes)), preserve_signposts=False)
    effect = ModifyRelationship(
        first.id, second.id, trade_volume_delta=40.0, reason="trade")
    effect.apply(world)
    route = next(iter(world.trade_routes.values()))
    initial_volume = world._route_trade_volume(route)

    for year in range(1, 81):
        world.current_year = year
        world._tick_trade_routes(year)
        if route.status == "abandoned":
            break

    assert world._route_trade_volume(route) < initial_volume
    assert route.status == "abandoned"
    assert route.closure_reason == "trade_inactive"


def test_overlapping_road_strokes_do_not_downgrade_bridge_tiles():
    width, height = 5, 2
    tiles = [0] * (width * height)
    tiles[1] = TILE_WATER
    roads = set()

    _paint_road(tiles, width, height, 0, 0, roads)
    assert tiles[1] == TILE_BRIDGE

    _paint_road(tiles, width, height, 1, 0, roads)

    assert tiles[1] == TILE_BRIDGE
    assert tiles[2] == TILE_ROAD


def test_single_character_distance_can_become_illegible_without_fallback():
    assert _obscure_text_character("1", seed=17) == "？"


def test_caravan_is_projected_only_into_its_current_cell():
    world = World(seed=440)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    assert len(route.path) >= 3
    group.path_index = 1
    current = WorldCellMapBuilder().build(world, *route.path[1])
    neighbor = WorldCellMapBuilder().build(world, *route.path[2])

    decorate_travel_groups(current, world)
    decorate_travel_groups(neighbor, world)

    caravans = [item for item in current["entities"]
                if item["kind"] == "caravan"]
    assert [item["id"] for item in caravans] == [group.id]
    assert caravans[0]["cargo"] == group.cargo
    assert not any(item["kind"] == "caravan"
                   for item in neighbor["entities"])


def test_active_wilderness_roads_have_grounded_moving_travelers():
    world = World(seed=439)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    assert len(route.path) >= 3
    road_travelers = [
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "traveler"
    ]
    pilgrim = next(
        item for item in road_travelers if item.traveler_role == "pilgrim")
    pilgrim.path_index = 1
    pilgrim.direction = 1
    pilgrim.origin_settlement_id = route.settlement_a_id
    pilgrim.destination_settlement_id = route.settlement_b_id
    pilgrim.progress_minutes = 0
    sample_map = WorldCellMapBuilder().build(world, *route.path[1])
    decorate_travel_groups(sample_map, world)
    travelers = [
        item for item in sample_map["entities"]
        if item["kind"] == "traveler"
    ]
    projected_pilgrim = next(
        item for item in travelers if item["id"] == pilgrim.id)

    assert len(projected_pilgrim["travel_path"]) >= 2
    assert projected_pilgrim["travel_clock_mode"] == "world_progress"
    assert projected_pilgrim["destination_name"] == (
        world.settlements[route.settlement_b_id].name)
    assert projected_pilgrim["religion_name"]
    assert (projected_pilgrim["religion_name"]
            in projected_pilgrim["dialogue_cn"]
            or projected_pilgrim["destination_name"]
            in projected_pilgrim["dialogue_cn"])

    simulation = LocalTimeSimulation(
        sample_map, world_seed=world.seed,
        location_id=f"{sample_map['cell']['x']},{sample_map['cell']['y']}",
    )
    positions = []
    for _ in range(12):
        positions.append({
            item["id"]: (item["x"], item["y"])
            for item in simulation.snapshot()["npcs"]
            if item["kind"] == "traveler"
        })
        simulation.advance(1)
    assert any(
        first[item_id] != second[item_id]
        for first, second in zip(positions, positions[1:])
        for item_id in first.keys() & second.keys())
    assert all(
        abs(first[item_id][0] - second[item_id][0])
        + abs(first[item_id][1] - second[item_id][1]) <= 1
        for first, second in zip(positions, positions[1:])
        for item_id in first.keys() & second.keys())
    assert pilgrim.progress_minutes == 0


def test_road_traveler_reaches_destination_then_starts_return_journey():
    world = World(seed=439)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    traveler = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "traveler")
    traveler.path_index = len(route.path) - 2
    traveler.direction = 1
    traveler.origin_settlement_id = route.settlement_a_id
    traveler.destination_settlement_id = route.settlement_b_id
    traveler.progress_minutes = 179

    world.advance_travel_groups(1)

    assert traveler.current_cell(route) == route.path[-1]
    assert traveler.destination_settlement_id == route.settlement_b_id
    assert traveler.status == "arrived"

    world.advance_travel_groups(179)
    assert traveler.current_cell(route) == route.path[-1]
    assert traveler.status == "arrived"

    world.advance_travel_groups(1)
    assert traveler.current_cell(route) == route.path[-2]
    assert traveler.destination_settlement_id == route.settlement_a_id
    assert traveler.status == "traveling"


def test_caravan_moves_tile_by_tile_inside_its_wilderness_cell():
    world = World(seed=440)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    group = next(item for item in world.travel_groups.values()
                 if item.route_id == route.id
                 and item.group_type == "caravan")
    group.path_index = 1
    group.direction = 1
    group.progress_minutes = 0
    local_map = WorldCellMapBuilder().build(world, *route.path[1])
    decorate_travel_groups(local_map, world)
    caravan = next(item for item in local_map["entities"]
                   if item["kind"] == "caravan")
    assert len(caravan["travel_path"]) >= 2
    local_map["entities"] = [
        item for item in local_map["entities"]
        if item["kind"] != "traveler"]
    simulation = LocalTimeSimulation(
        local_map, world_seed=world.seed,
        location_id=f"{route.path[1][0]},{route.path[1][1]}")
    positions = []
    for _ in range(12):
        npc = next(item for item in simulation.snapshot()["npcs"]
                   if item["id"] == group.id)
        positions.append((npc["x"], npc["y"]))
        simulation.advance(1)

    assert len(set(positions)) > 1
    assert all(
        abs(first[0] - second[0]) + abs(first[1] - second[1]) <= 1
        for first, second in zip(positions, positions[1:]))
    assert group.progress_minutes == 0


def test_open_local_map_refreshes_when_caravan_leaves_cell():
    world = World(seed=441)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    group.path_index = 0
    group.direction = 1
    group.progress_minutes = 179
    session = PlayerSession(world, route.settlement_a_id)
    original_position = dict(session.local_time.player)
    session.local_time._explored_cells = {
        (original_position["x"], original_position["y"]),
        (max(0, original_position["x"] - 1), original_position["y"]),
    }
    original_explored = set(session.local_time._explored_cells)

    assert any(item["id"] == group.id
               for item in session.local_map["entities"])

    result = session.wait(5)

    assert result["local_map"] is session.local_map
    assert not any(item["id"] == group.id
                   for item in result["local_map"]["entities"])
    assert session.local_time.player == original_position
    assert session.local_time.turn == 5
    assert original_explored <= session.local_time._explored_cells
    assert group.current_cell(route) == route.path[1]


def test_wilderness_maps_are_lazy_and_reused():
    world = World(seed=433)
    world.generate(years=0)
    occupied = {
        (int(item.grid_x), int(item.grid_y))
        for item in world.settlements.values()
    }
    cell = next(
        (x, y)
        for y in range(world.geography.height)
        for x in range(world.geography.width)
        if (x, y) not in occupied
        and str(world.geography.biomes[y, x]) not in {"ocean", "lake"}
    )
    repository = LocalMapRepository(world)

    first = repository.get(*cell)
    second = repository.get(*cell)

    assert first is second
    assert first["site_type"] == "wilderness"
    assert first["cell"] == {"x": cell[0], "y": cell[1]}
    assert len(repository.maps) == 1


def test_wilderness_has_dense_ecology_traces_and_moving_wildlife():
    world = World(seed=442)
    world.generate(years=0)
    geography = world.geography
    cells = []
    seen_biomes = set()
    for y in range(geography.height):
        for x in range(geography.width):
            biome = str(geography.biomes[y, x])
            if biome in {"ocean", "lake"} or biome in seen_biomes:
                continue
            seen_biomes.add(biome)
            cells.append((x, y))
            if len(cells) == 4:
                break
        if len(cells) == 4:
            break

    maps = [WorldCellMapBuilder().build(world, *cell) for cell in cells]

    assert all(45 <= len(local_map["decorations"]) <= 75
               for local_map in maps)
    assert all(any(item["kind"] == "trace"
                   for item in local_map["entities"])
               for local_map in maps)
    assert all(any(item["kind"] == "wildlife"
                   for item in local_map["entities"])
               for local_map in maps)
    assert len({
        item["subtype"]
        for local_map in maps for item in local_map["decorations"]
    }) >= 6

    local_map = maps[0]
    repeated = WorldCellMapBuilder().build(world, *cells[0])
    assert local_map["decorations"] == repeated["decorations"]
    wildlife = {
        item["id"]: (item["x"], item["y"])
        for item in local_map["entities"] if item["kind"] == "wildlife"
    }
    simulation = LocalTimeSimulation(
        local_map, world_seed=world.seed,
        location_id=f"{cells[0][0]},{cells[0][1]}",
        biome=str(geography.biomes[cells[0][1], cells[0][0]]),
    )

    runtime = simulation.advance(30)
    moved_wildlife = {
        item["id"]: (item["x"], item["y"])
        for item in runtime["npcs"] if item["kind"] == "wildlife"
    }

    assert moved_wildlife.keys() == wildlife.keys()
    assert any(moved_wildlife[item_id] != position
               for item_id, position in wildlife.items())


def test_trade_road_uses_matching_normalized_edge_portals():
    world = World(seed=434)
    world.generate(years=0)
    _, _, route = _overland_route(world)
    assert len(route.path) >= 2
    first, second = route.path[0], route.path[1]
    first_map = LocalMapRepository(world).get(*first)
    second_map = LocalMapRepository(world).get(*second)
    shared_segment_id = road_segment_id(first, second)
    first_portal = next(
        portals[0] for segment_id, portals in route_portals(
            world, *first, first_map["width"], first_map["height"])
        if segment_id == shared_segment_id)
    second_portal = next(
        portals[0] for segment_id, portals in route_portals(
            world, *second, second_map["width"], second_map["height"])
        if segment_id == shared_segment_id)

    if first[0] != second[0]:
        first_fraction = first_portal[1] / (first_map["height"] - 1)
        second_fraction = second_portal[1] / (second_map["height"] - 1)
    else:
        first_fraction = first_portal[0] / (first_map["width"] - 1)
        second_fraction = second_portal[0] / (second_map["width"] - 1)
    assert abs(first_fraction - second_fraction) <= 0.02
    assert first_map["tiles"][
        first_portal[1] * first_map["width"] + first_portal[0]
    ] in {TILE_ROAD, TILE_BRIDGE}
    assert second_map["tiles"][
        second_portal[1] * second_map["width"] + second_portal[0]
    ] in {TILE_ROAD, TILE_BRIDGE}


def test_cardinal_river_cells_share_a_water_portal():
    world = World(seed=435)
    world.generate(years=0)
    geography = world.geography
    pair = next(
        ((x, y), (nx, ny))
        for y in range(geography.height)
        for x in range(geography.width)
        if str(geography.biomes[y, x]) == "river"
        for nx, ny in ((x + 1, y), (x, y + 1))
        if nx < geography.width and ny < geography.height
        and str(geography.biomes[ny, nx]) == "river"
    )
    first = WorldCellMapBuilder().build(world, *pair[0])
    second = WorldCellMapBuilder().build(world, *pair[1])
    if pair[0][0] != pair[1][0]:
        first_edge = [
            first["tiles"][y * first["width"] + first["width"] - 1]
            for y in range(first["height"])]
        second_edge = [
            second["tiles"][y * second["width"]]
            for y in range(second["height"])]
    else:
        first_edge = first["tiles"][-first["width"]:]
        second_edge = second["tiles"][:second["width"]]
    assert first_edge == second_edge
    assert TILE_WATER in first_edge


def test_diagonal_river_connections_use_matching_map_corners():
    world = World(seed=42)
    world.generate(years=0)
    geography = world.geography
    (x, y), (dx, dy) = next(
        ((x, y), (dx, dy))
        for y in range(geography.height)
        for x in range(geography.width)
        if geography.rivers[y, x]
        for dx, dy in geography.river_connections(x, y)
        if abs(dx) == 1 and abs(dy) == 1
        and geography.rivers[y + dy, x + dx]
    )
    builder = WorldCellMapBuilder()
    width, height = 80, 56
    first_tiles = [TILE_GRASS] * (width * height)
    second_tiles = [TILE_GRASS] * (width * height)

    builder._paint_river(first_tiles, geography, x, y, width, height)
    builder._paint_river(
        second_tiles, geography, x + dx, y + dy, width, height)

    first_corner = (
        width - 1 if dx > 0 else 0,
        height - 1 if dy > 0 else 0,
    )
    second_corner = (
        0 if dx > 0 else width - 1,
        0 if dy > 0 else height - 1,
    )
    assert first_tiles[first_corner[1] * width + first_corner[0]] == TILE_WATER
    assert second_tiles[
        second_corner[1] * width + second_corner[0]] == TILE_WATER


def test_wilderness_river_widths_create_fords_and_reciprocal_ferries():
    world = World(seed=439)
    world.generate(years=0)
    builder = WorldCellMapBuilder()
    maps_by_radius = {}
    cells_by_radius = {}
    for y in range(world.geography.height):
        for x in range(world.geography.width):
            if str(world.geography.biomes[y, x]) != "river":
                continue
            radius = world.geography.river_radius(x, y)
            if radius in maps_by_radius:
                continue
            local_map = builder.build(world, x, y)
            if TILE_BRIDGE in local_map["tiles"]:
                continue
            if radius <= 2 and TILE_FORD not in local_map["tiles"]:
                continue
            if (radius == 3 and len([
                    item for item in local_map["entities"]
                    if item.get("subtype") == "ferry"]) != 2):
                continue
            maps_by_radius[radius] = local_map
            cells_by_radius[radius] = (x, y)
        if set(maps_by_radius) == {1, 2, 3}:
            break

    assert set(maps_by_radius) == {1, 2, 3}
    assert TILE_FORD not in BLOCKING_TILES
    assert maps_by_radius[1]["profile"]["water_radius"] == 1
    assert maps_by_radius[2]["profile"]["water_radius"] == 2
    assert maps_by_radius[3]["profile"]["water_radius"] == 3

    narrow_map = maps_by_radius[1]
    ford_tiles = {
        (index % narrow_map["width"], index // narrow_map["width"])
        for index, tile in enumerate(narrow_map["tiles"])
        if tile == TILE_FORD
    }
    start, ford = next(
        ((x, y), (x + dx, y + dy))
        for x, y in ford_tiles
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1))
        if (x + dx, y + dy) in ford_tiles)
    land_neighbors = {
        (x + dx, y + dy)
        for x, y in ford_tiles
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1))
        if 0 <= x + dx < narrow_map["width"]
        and 0 <= y + dy < narrow_map["height"]
        and narrow_map["tiles"][
            (y + dy) * narrow_map["width"] + x + dx
        ] not in BLOCKING_TILES | {TILE_FORD}
    }
    assert len(land_neighbors) >= 2
    session = PlayerSession(world)
    session.current_cell = cells_by_radius[1]
    session.current_location_id = None
    session.local_map = narrow_map
    session.local_time = LocalTimeSimulation(
        narrow_map, world_seed=world.seed,
        location_id=f"{session.current_cell[0]},{session.current_cell[1]}",
        biome="river", player_position=start)
    dx, dy = ford[0] - start[0], ford[1] - start[1]

    with pytest.raises(PlayerActionError, match="只能步行涉水"):
        session.move(dx, dy, movement_mode="run")
    crossing = session.move(dx, dy, movement_mode="walk")

    assert crossing["moved"]
    assert crossing["elapsed_minutes"] == 2.0
    assert session.local_time.player == {"x": ford[0], "y": ford[1]}

    wide_map = maps_by_radius[3]
    ferries = [
        item for item in wide_map["entities"]
        if item.get("subtype") == "ferry"]
    first, second = ferries
    assert first["ferry_target"] == {"x": second["x"], "y": second["y"]}
    assert second["ferry_target"] == {"x": first["x"], "y": first["y"]}
    session.current_cell = cells_by_radius[3]
    session.local_map = wide_map
    session.local_time = LocalTimeSimulation(
        wide_map, world_seed=world.seed,
        location_id=f"{session.current_cell[0]},{session.current_cell[1]}",
        biome="river", player_position=(first["x"], first["y"]))

    ferry_result = session.use_ferry(first["id"])

    assert ferry_result["elapsed_minutes"] == 10
    assert session.local_time.player == {"x": second["x"], "y": second["y"]}


def test_watercourse_rasterizes_a_diagonal_instead_of_an_l_shape():
    width = height = 21
    tiles = [TILE_GRASS] * (width * height)

    _carve_water(tiles, width, height, (0, 0), (20, 20))

    assert tiles[10 * width + 10] == TILE_WATER
    assert tiles[2 * width + 18] == TILE_GRASS
    assert tiles[18 * width + 2] == TILE_GRASS


def test_settlement_roads_build_walkable_bridges_across_diagonal_river():
    width, height = 60, 42
    profile = SettlementMapProfile(
        width=width,
        height=height,
        layout_type="river",
        water_axis="diagonal_down",
        water_side="east",
        hub=(width // 2, height // 2),
        entrances=(),
        base_tile=TILE_GRASS,
        landscape_type="plains",
        landscape_name="测试河谷",
        feature_names=(),
        watercourse=((9, 0), (50, 41)),
    )
    tiles = [TILE_GRASS] * (width * height)
    paint_watercourse(tiles, width, height, profile.watercourse, radius=1)

    roads = LocalMapBuilder()._roads(
        tiles, profile, type("WorldStub", (), {"seed": 1})(),
        type("SettlementStub", (), {"id": "diagonal-river"})())
    bridge_positions = {
        (index % width, index // width)
        for index, tile in enumerate(tiles)
        if tile == TILE_BRIDGE
    }

    assert len(bridge_positions) >= 6
    assert bridge_positions <= roads
    assert TILE_BRIDGE not in BLOCKING_TILES

    start = next(iter(bridge_positions))
    reached = {start}
    frontier = deque([start])
    while frontier:
        x, y = frontier.popleft()
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            neighbor = (x + dx, y + dy)
            if neighbor in roads and neighbor not in reached:
                reached.add(neighbor)
                frontier.append(neighbor)
    touched_edges = {
        edge
        for x, y in reached
        for edge, touches in (
            ("north", y == 3), ("south", y == height - 4),
            ("west", x == 3), ("east", x == width - 4),
        )
        if touches
    }
    assert len(touched_edges) >= 2


def test_wilderness_profile_uses_its_named_geographic_feature():
    world = World(seed=42)
    world.generate(years=0)
    feature = next(
        item for item in world.geography.features
        if item.feature_type in {"river", "mountain", "plains"})
    local_map = WorldCellMapBuilder().build(world, *feature.anchor)

    assert local_map["profile"]["landscape_name"] == feature.name
    assert feature.name in local_map["profile"]["feature_names"]


@pytest.mark.parametrize(
    ("movement_mode", "elapsed_minutes"),
    [("walk", 1.0), ("run", 0.5)],
)
def test_player_can_cross_a_walkable_land_boundary(
        movement_mode, elapsed_minutes):
    world = World(seed=436)
    world.generate(years=0)
    session = PlayerSession(world)
    geography = world.geography
    directions = (
        ("north", 0, -1), ("south", 0, 1),
        ("west", -1, 0), ("east", 1, 0),
    )
    for direction, dx, dy in directions:
        target = (session.current_cell[0] + dx, session.current_cell[1] + dy)
        if not (0 <= target[0] < geography.width
                and 0 <= target[1] < geography.height):
            continue
        if str(geography.biomes[target[1], target[0]]) in {"ocean", "lake"}:
            continue
        width, height = session.local_map["width"], session.local_map["height"]
        edge = (
            [(x, 0) for x in range(width)] if direction == "north" else
            [(x, height - 1) for x in range(width)] if direction == "south" else
            [(0, y) for y in range(height)] if direction == "west" else
            [(width - 1, y) for y in range(height)]
        )
        blocking = set(session.local_map["blocking_tiles"])
        position = next((
            item for item in edge
            if session.local_map["tiles"][item[1] * width + item[0]]
            not in blocking
        ), None)
        if position is None:
            continue
        session.local_time.player = {"x": position[0], "y": position[1]}
        result = session.move(dx, dy, movement_mode)
        assert result["changed_map"]
        assert result["movement_mode"] == movement_mode
        assert result["elapsed_minutes"] == elapsed_minutes
        assert session.current_cell == target
        assert result["location"]["local_map"] is session.local_map
        return
    pytest.skip("starting settlement has no walkable land boundary")


def test_ruins_cannot_be_fast_travel_destinations():
    world = World(seed=437)
    world.generate(years=0)
    session = PlayerSession(world)
    ruin = next(
        item for item in world.settlements.values()
        if item.id != session.current_location_id)
    ruin.alive = False

    with pytest.raises(PlayerActionError, match="快速旅行"):
        session.travel(ruin.id)
