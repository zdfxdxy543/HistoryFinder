"""Persistent multi-cell wilderness camp lifecycle tests."""

import json
from itertools import combinations

from game.local_map import BLOCKING_TILES, TILE_WATER
from game.world_cell_map import WorldCellMapBuilder, decorate_travel_groups
from simulation.camps import (
    CAMP_EMBERS_MINUTES,
    CAMP_ERASED_MINUTES,
    CAMP_WEATHERED_MINUTES,
    WildernessCamp,
)
from simulation.world import World


def _overland_route(world):
    for first, second in combinations(
            sorted(world.settlements.values(), key=lambda item: item.id), 2):
        route = world.ensure_trade_route(first.id, second.id)
        if route is not None and len(route.path) >= 3:
            return route
    raise AssertionError("test world has no route with wilderness cells")


def test_camp_trace_lifecycle_is_persistent_and_monotonic():
    camp = WildernessCamp(
        id="camp_test",
        world_cell=(10, 12),
        camp_type="caravan",
        state="occupied",
        layout_seed=42,
        established_minute=0,
        state_changed_minute=0,
        last_occupied_minute=0,
        owner_group_id="caravan_test",
    )

    camp.vacate(60)
    assert camp.state == "embers"
    assert camp.owner_group_id == ""
    camp.weather_to(60 + CAMP_EMBERS_MINUTES)
    assert camp.state == "abandoned"
    camp.weather_to(60 + CAMP_EMBERS_MINUTES + CAMP_WEATHERED_MINUTES)
    assert camp.state == "weathered"
    camp.weather_to(
        60 + CAMP_EMBERS_MINUTES + CAMP_WEATHERED_MINUTES
        + CAMP_ERASED_MINUTES)
    assert camp.state == "erased"

    restored = WildernessCamp.from_dict(json.loads(json.dumps(camp.to_dict())))
    assert restored.to_dict() == camp.to_dict()


def test_caravan_camps_at_night_and_leaves_embers_at_dawn():
    world = World(seed=461)
    world.generate(years=0)
    route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    group.path_index = 1
    group.progress_minutes = 0
    cell = route.path[1]
    world.travel_clock_minutes = 18 * 60 + 59

    world.advance_travel_groups(1)

    occupied = next(
        camp for camp in world.get_camps_at(*cell)
        if camp.owner_group_id == group.id)
    assert occupied.state == "occupied"
    assert group.status == "camped"
    assert group.progress_minutes == 0

    world.advance_travel_groups(11 * 60)

    assert occupied.state == "embers"
    assert occupied.owner_group_id == ""
    assert group.status == "traveling"
    assert group.progress_minutes == 1


def test_camp_projects_multiple_specialized_entities_without_changing_tiles():
    world = World(seed=462)
    world.generate(years=0)
    route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    group.path_index = 1
    group.progress_minutes = 0
    cell = route.path[1]
    world.travel_clock_minutes = 19 * 60
    world.advance_travel_groups(1)
    camp = next(
        item for item in world.get_camps_at(*cell)
        if item.owner_group_id == group.id)
    local_map = WorldCellMapBuilder().build(world, *cell)
    original_tiles = list(local_map["tiles"])

    decorate_travel_groups(local_map, world)

    components = [
        item for item in local_map["entities"]
        if item.get("camp_id") == camp.id]
    assert len(components) == 7
    assert len({(item["x"], item["y"]) for item in components}) == 7
    assert {
        "camp_tent_large", "camp_tent_small", "campfire_burning",
        "camp_wagon", "camp_supplies", "camp_tether", "camp_bedroll",
    } == {item["component_type"] for item in components}
    assert any(item["blocks_movement"] for item in components)
    assert any(not item["blocks_movement"] for item in components)
    assert local_map["tiles"] == original_tiles
    assert all(
        local_map["tiles"][item["y"] * local_map["width"] + item["x"]]
        not in BLOCKING_TILES | {TILE_WATER}
        for item in components)


def test_world_roundtrip_preserves_camps_and_travel_clock():
    world = World(seed=463)
    world.generate(years=0)
    route = _overland_route(world)
    group = next(
        item for item in world.travel_groups.values()
        if item.route_id == route.id and item.group_type == "caravan")
    group.path_index = 1
    world.travel_clock_minutes = 19 * 60
    world.advance_travel_groups(1)

    restored = World.from_dict(json.loads(json.dumps(world.to_dict())))

    assert restored.travel_clock_minutes == world.travel_clock_minutes
    assert {
        key: camp.to_dict() for key, camp in restored.wilderness_camps.items()
    } == {
        key: camp.to_dict() for key, camp in world.wilderness_camps.items()
    }
