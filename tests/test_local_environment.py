from game.local_time import LocalTimeSimulation, WEATHER_BY_BIOME


def _local_map(*, wall: bool = False, water: bool = False,
               fence: bool = False) -> dict:
    width = 9
    height = 9
    tiles = [0] * (width * height)
    if wall:
        for y in range(height):
            tiles[y * width + 4] = 3
    if water:
        for y in range(height):
            tiles[y * width + 4] = 4
    if fence:
        for y in range(height):
            tiles[y * width + 4] = 17
    return {
        "width": width,
        "height": height,
        "tiles": tiles,
        "blocking_tiles": [3, 4, 17],
        "player_start": {"x": 2, "y": 4},
        "entities": [],
        "buildings": [],
        "zones": [],
        "profile": {"hub": {"x": 4, "y": 4}},
    }


def _coordinates(items: list[dict]) -> set[tuple[int, int]]:
    return {(item["x"], item["y"]) for item in items}


def test_environment_is_deterministic_for_world_place_and_time():
    first = LocalTimeSimulation(
        _local_map(), day=7, minute_of_day=13 * 60,
        world_seed=42, location_id="settlement-4", biome="forest",
    )
    second = LocalTimeSimulation(
        _local_map(), day=7, minute_of_day=13 * 60,
        world_seed=42, location_id="settlement-4", biome="forest",
    )

    assert first.snapshot()["environment"] == second.snapshot()["environment"]


def test_biomes_only_select_weather_from_their_catalog():
    for biome in ("tundra", "desert", "forest", "river_valley"):
        simulation = LocalTimeSimulation(
            _local_map(), world_seed=84, location_id="weather-test", biome=biome,
        )
        generated = set()
        for day in range(1, 7):
            for hour in range(0, 24, 3):
                simulation.day = day
                simulation.minute_of_day = hour * 60
                generated.add(simulation.snapshot()["environment"]["weather"])
        assert generated <= set(WEATHER_BY_BIOME[biome])


def test_daylight_controls_light_and_clear_weather_visibility():
    simulation = LocalTimeSimulation(_local_map())
    simulation._weather = lambda: "clear"

    simulation.minute_of_day = 12 * 60
    day = simulation.snapshot()["environment"]
    simulation.minute_of_day = 2 * 60
    late_night = simulation.snapshot()["environment"]

    assert day["daylight"] == "day"
    assert day["light_level"] == 1.0
    assert day["visibility_radius"] == 10
    assert late_night["daylight"] == "late_night"
    assert late_night["light_level"] < day["light_level"]
    assert late_night["visibility_radius"] == 4


def test_walls_are_visible_but_hide_tiles_behind_them():
    simulation = LocalTimeSimulation(_local_map(wall=True))
    simulation._weather = lambda: "clear"
    visible = _coordinates(simulation.snapshot()["visible_tiles"])

    assert (4, 4) in visible
    assert (5, 4) not in visible
    assert (3, 4) in visible


def test_water_blocks_movement_without_blocking_sight():
    simulation = LocalTimeSimulation(_local_map(water=True))
    simulation._weather = lambda: "clear"
    visible = _coordinates(simulation.snapshot()["visible_tiles"])

    assert (4, 4) in visible
    assert (5, 4) in visible

    simulation.player = {"x": 3, "y": 4}
    movement = simulation.move_player(1, 0)

    assert not movement["moved"]
    assert simulation.player == {"x": 3, "y": 4}


def test_fence_blocks_movement_without_blocking_sight():
    simulation = LocalTimeSimulation(_local_map(fence=True))
    simulation._weather = lambda: "clear"
    visible = _coordinates(simulation.snapshot()["visible_tiles"])

    assert (4, 4) in visible
    assert (5, 4) in visible

    simulation.player = {"x": 3, "y": 4}
    movement = simulation.move_player(1, 0)

    assert not movement["moved"]
    assert simulation.player == {"x": 3, "y": 4}


def test_explored_tiles_remain_after_the_player_moves():
    simulation = LocalTimeSimulation(_local_map())
    simulation._weather = lambda: "clear"
    simulation.minute_of_day = 2 * 60
    first = _coordinates(simulation.snapshot()["explored_tiles"])

    simulation.player = {"x": 6, "y": 4}
    second = _coordinates(simulation.snapshot()["explored_tiles"])

    assert first < second
    assert (0, 4) in first
    assert (8, 4) in second


def test_half_minute_ticks_keep_npcs_on_full_minute_updates():
    simulation = LocalTimeSimulation(_local_map(), minute_of_day=8 * 60)
    npc_updates = []
    simulation._move_npcs_one_tick = lambda: npc_updates.append(
        simulation.minute_of_day)

    first = simulation.advance(0.5)
    second = simulation.advance(0.5)

    assert first["time_label"] == "08:00:30"
    assert first["turn"] == 0.5
    assert npc_updates == [8 * 60 + 1]
    assert second["time_label"] == "08:01"
