"""Turn-based local time, movement, and deterministic NPC schedules."""

from __future__ import annotations

import hashlib
from collections import deque

from game.local_map import TILE_FENCE, TILE_WATER


DAYLIGHT_NAMES = {
    "dawn": "黎明",
    "day": "白昼",
    "dusk": "黄昏",
    "night": "夜晚",
    "late_night": "深夜",
}


WEATHER_NAMES = {
    "clear": "晴朗",
    "cloudy": "多云",
    "rain": "降雨",
    "storm": "风暴",
    "fog": "雾",
    "snow": "降雪",
    "dust": "扬尘",
}


WEATHER_BY_BIOME = {
    "tundra": ("clear", "cloudy", "cloudy", "fog", "snow", "snow"),
    "mountain": ("clear", "cloudy", "cloudy", "fog", "rain", "snow"),
    "highland": ("clear", "clear", "cloudy", "fog", "rain", "storm"),
    "desert": ("clear", "clear", "clear", "cloudy", "dust", "dust"),
    "scrubland": ("clear", "clear", "cloudy", "rain", "dust"),
    "forest": ("clear", "cloudy", "cloudy", "rain", "rain", "fog", "storm"),
    "river_valley": ("clear", "cloudy", "rain", "rain", "fog", "storm"),
    "grassland": ("clear", "clear", "cloudy", "rain", "storm", "fog"),
    "plains": ("clear", "clear", "cloudy", "rain", "storm", "fog"),
}


WEATHER_VISIBILITY_PENALTY = {
    "clear": 0,
    "cloudy": 0,
    "rain": 1,
    "storm": 3,
    "fog": 4,
    "snow": 2,
    "dust": 3,
}


ACTIVITY_NAMES = {
    "commuting": "正在上工",
    "working": "正在工作",
    "midday": "正在午间外出",
    "going_home": "正在回家",
    "resting": "正在家中休息",
    "foraging": "正在觅食",
    "traveling": "正在赶路",
}


WORKPLACE_TYPES = {
    "scholar": ("library", "archive"),
    "scribe": ("archive", "hall"),
    "elder": ("hall",),
    "merchant": ("great_market", "market"),
    "artisan": ("workshop",),
    "farmer": ("field", "mill"),
    "weaver": ("workshop",),
    "porter": ("great_market", "market", "dock", "granary"),
    "baker": ("bakery",),
    "vendor": ("great_market", "market"),
    "water_carrier": ("aqueduct", "cistern", "well", "market"),
    "carpenter": ("workshop", "lumberyard"),
    "inn_worker": ("inn",),
    "laborer": ("granary", "quarry", "lumberyard", "dock"),
}


BREAK_PLACE_TYPES = (
    "great_market", "market", "well", "inn", "hall", "temple",
    "library", "palace", "dock",
)


class LocalTimeSimulation:
    """Authoritative local clock and movement state for one player session."""

    tick_minutes = 1

    def __init__(self, local_map: dict, day: int = 1,
                 minute_of_day: int = 6 * 60 + 55,
                 settle_npcs: bool = False, *, world_seed: int = 0,
                 location_id: str = "local", biome: str = "plains",
                 player_position: tuple[int, int] | None = None,
                 full_map_vision: bool = False):
        self.local_map = local_map
        self.day = max(1, day)
        self.minute_of_day = minute_of_day % (24 * 60)
        self.world_seed = world_seed
        self.location_id = location_id
        self.biome = biome
        self.full_map_vision = full_map_vision
        self.turn = 0
        self.player = (
            {"x": player_position[0], "y": player_position[1]}
            if player_position is not None else dict(local_map["player_start"])
        )
        self._static_positions = {
            (item["x"], item["y"])
            for item in local_map["entities"]
            if (item["kind"] not in {
                "informant", "resident", "caravan", "traveler", "wildlife"}
                and item.get("blocks_movement", True))
        }
        self._reachable_cells = self._reachable_from_player_start()
        self._explored_cells: set[tuple[int, int]] = set()
        self._npcs: dict[str, dict] = {}
        self._initialize_npcs()
        if settle_npcs:
            self._settle_npcs_at_current_time()

    def move_player(self, dx: int, dy: int) -> dict:
        if abs(dx) + abs(dy) != 1:
            raise ValueError("移动必须是相邻的一个格子。")
        target = (self.player["x"] + dx, self.player["y"] + dy)
        if not self._in_bounds(target):
            direction = (
                "west" if target[0] < 0 else
                "east" if target[0] >= self.local_map["width"] else
                "north" if target[1] < 0 else "south"
            )
            offset = self.player["y"] if dx else self.player["x"]
            span = self.local_map["height"] if dx else self.local_map["width"]
            return {
                "moved": False,
                "exit_map": {
                    "direction": direction,
                    "offset": offset,
                    "span": span,
                },
                "runtime": self.snapshot(),
            }
        occupied = {
            (npc["x"], npc["y"])
            for npc in self._npcs.values()
            if npc["kind"] != "wildlife"
        }
        if (not self._is_walkable(target) or target in occupied
                or target in self._static_positions):
            return {"moved": False, "runtime": self.snapshot()}
        self.player = {"x": target[0], "y": target[1]}
        self.advance(self.tick_minutes)
        return {"moved": True, "runtime": self.snapshot()}

    def advance(self, minutes: int) -> dict:
        if minutes <= 0 or minutes % self.tick_minutes:
            raise ValueError("时间必须按 1 分钟的整数倍推进。")
        for _ in range(minutes // self.tick_minutes):
            self.turn += 1
            self.minute_of_day += self.tick_minutes
            if self.minute_of_day >= 24 * 60:
                self.minute_of_day -= 24 * 60
                self.day += 1
            self._move_npcs_one_tick()
        return self.snapshot()

    def snapshot(self) -> dict:
        hour, minute = divmod(self.minute_of_day, 60)
        environment = self._environment_snapshot()
        natural_visible = self._visible_cells(environment["visibility_radius"])
        self._explored_cells.update(natural_visible)
        visible_cells = (
            {
                (x, y)
                for y in range(self.local_map["height"])
                for x in range(self.local_map["width"])
            }
            if self.full_map_vision else natural_visible
        )
        return {
            "day": self.day,
            "minute_of_day": self.minute_of_day,
            "time_label": f"{hour:02d}:{minute:02d}",
            "period_name": self._period_name(hour),
            "turn": self.turn,
            "full_map_vision": self.full_map_vision,
            "player": dict(self.player),
            "environment": environment,
            "visible_tiles": self._sorted_cells(visible_cells),
            "explored_tiles": self._sorted_cells(self._explored_cells),
            "npcs": [
                {
                    "id": npc["id"],
                    "kind": npc["kind"],
                    "x": npc["x"],
                    "y": npc["y"],
                    "activity": npc["activity"],
                    "activity_name": ACTIVITY_NAMES[npc["activity"]],
                }
                for npc in sorted(self._npcs.values(), key=lambda item: item["id"])
            ],
        }

    def _environment_snapshot(self) -> dict:
        daylight, light_level, base_radius = self._daylight()
        weather = self._weather()
        radius = max(
            2,
            base_radius - WEATHER_VISIBILITY_PENALTY[weather],
        )
        return {
            "daylight": daylight,
            "daylight_name": DAYLIGHT_NAMES[daylight],
            "light_level": light_level,
            "weather": weather,
            "weather_name": WEATHER_NAMES[weather],
            "visibility_radius": radius,
        }

    def _daylight(self) -> tuple[str, float, int]:
        minute = self.minute_of_day
        if 5 * 60 <= minute < 7 * 60:
            return "dawn", 0.58, 7
        if 7 * 60 <= minute < 17 * 60:
            return "day", 1.0, 10
        if 17 * 60 <= minute < 19 * 60:
            return "dusk", 0.52, 7
        if 19 * 60 <= minute < 23 * 60:
            return "night", 0.28, 5
        return "late_night", 0.18, 4

    def _weather(self) -> str:
        choices = WEATHER_BY_BIOME.get(
            self.biome,
            ("clear", "clear", "cloudy", "rain", "fog", "storm"),
        )
        weather_block = self.minute_of_day // (3 * 60)
        digest = hashlib.sha256(
            f"weather|{self.world_seed}|{self.location_id}|"
            f"{self.day}|{weather_block}".encode("utf-8")
        ).digest()
        return choices[int.from_bytes(digest[:4], "big") % len(choices)]

    def _visible_cells(self, radius: int) -> set[tuple[int, int]]:
        origin = (self.player["x"], self.player["y"])
        visible = {origin}
        width = self.local_map["width"]
        height = self.local_map["height"]
        for y in range(max(0, origin[1] - radius),
                       min(height, origin[1] + radius + 1)):
            for x in range(max(0, origin[0] - radius),
                           min(width, origin[0] + radius + 1)):
                if max(abs(x - origin[0]), abs(y - origin[1])) > radius:
                    continue
                target = (x, y)
                if self._has_line_of_sight(origin, target):
                    visible.add(target)
        return visible

    def _has_line_of_sight(self, origin: tuple[int, int],
                           target: tuple[int, int]) -> bool:
        line = self._grid_line(origin, target)
        # The blocking tile can be seen; only cells behind it are hidden.
        return not any(self._blocks_sight(cell) for cell in line[1:-1])

    def _blocks_sight(self, position: tuple[int, int]) -> bool:
        x, y = position
        tile = self.local_map["tiles"][y * self.local_map["width"] + x]
        return (
            tile in self.local_map["blocking_tiles"]
            and tile not in {TILE_WATER, TILE_FENCE}
        )

    @staticmethod
    def _grid_line(origin: tuple[int, int],
                   target: tuple[int, int]) -> list[tuple[int, int]]:
        x0, y0 = origin
        x1, y1 = target
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = dx + dy
        line = []
        while True:
            line.append((x0, y0))
            if x0 == x1 and y0 == y1:
                return line
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += step_x
            if doubled <= dx:
                error += dx
                y0 += step_y

    @staticmethod
    def _sorted_cells(cells: set[tuple[int, int]]) -> list[dict]:
        return [
            {"x": x, "y": y}
            for x, y in sorted(cells, key=lambda item: (item[1], item[0]))
        ]

    def _initialize_npcs(self) -> None:
        homes = self._home_positions()
        fallback = self._fallback_positions()
        if not homes:
            homes = fallback
        breaks = self._positions_for_places(BREAK_PLACE_TYPES) or fallback
        assigned_homes: set[tuple[int, int]] = set()
        assigned_work: set[tuple[int, int]] = set()
        assigned_breaks: set[tuple[int, int]] = set()
        npcs = [
            item for item in self.local_map["entities"]
            if item["kind"] in {
                "informant", "resident", "caravan", "traveler", "wildlife"}
        ]
        for index, entity in enumerate(sorted(npcs, key=lambda item: item["id"])):
            travel_path = [
                (int(item[0]), int(item[1]))
                for item in entity.get("travel_path", [])
                if (self._in_bounds((int(item[0]), int(item[1])))
                    and self._is_walkable((int(item[0]), int(item[1]))))
            ]
            travel_mode = str(entity.get("travel_clock_mode", ""))
            travel_cursor = 0
            travel_progress = int(entity.get("travel_progress", 0))
            travel_duration = max(1, int(entity.get("travel_duration", 180)))
            if travel_path and travel_mode == "loop":
                cycle = max(1, 2 * len(travel_path) - 2)
                absolute_minute = (self.day - 1) * 24 * 60 + self.minute_of_day
                travel_cursor = (
                    absolute_minute + int(entity.get("travel_offset", 0))) % cycle
                path_index = (travel_cursor if travel_cursor < len(travel_path)
                              else cycle - travel_cursor)
                home = travel_path[path_index]
                work = travel_path[-1]
                midday = travel_path[len(travel_path) // 2]
            elif travel_path and travel_mode == "world_progress":
                path_index = min(
                    len(travel_path) - 1,
                    int(travel_progress / travel_duration
                        * (len(travel_path) - 1)),
                )
                home = travel_path[path_index]
                work = travel_path[-1]
                midday = travel_path[len(travel_path) // 2]
            elif entity["kind"] == "wildlife":
                home = (entity["x"], entity["y"])
                roam = self._wildlife_roam_positions(home, entity["id"])
                work = roam[0]
                midday = roam[1] if len(roam) > 1 else home
            else:
                home = self._assign_target(homes, assigned_homes, index)
                workplaces = self._positions_for_places(
                    WORKPLACE_TYPES.get(entity["role"], BREAK_PLACE_TYPES))
                work = self._assign_target(
                    workplaces or fallback,
                    assigned_work,
                    index,
                )
                midday = self._assign_target(
                    breaks, assigned_breaks, index)
            entity["x"], entity["y"] = home
            self._npcs[entity["id"]] = {
                "id": entity["id"],
                "kind": entity["kind"],
                "x": home[0],
                "y": home[1],
                "home": home,
                "work": work,
                "midday": midday,
                "schedule_offset": self._schedule_offset(entity["id"]),
                "activity": "traveling" if travel_path else "resting",
                "path_target": None,
                "path": [],
                "travel_path": travel_path,
                "travel_mode": travel_mode,
                "travel_cursor": travel_cursor,
                "travel_progress": travel_progress,
                "travel_duration": travel_duration,
            }

    def _wildlife_roam_positions(
            self, origin: tuple[int, int], entity_id: str
    ) -> list[tuple[int, int]]:
        candidates = [
            position for position in self._reachable_cells
            if (4 <= abs(position[0] - origin[0])
                + abs(position[1] - origin[1]) <= 12
                and position not in self._static_positions
                and self._is_walkable(position))
        ]
        candidates.sort(key=lambda position: hashlib.sha256(
            f"wildlife-roam|{entity_id}|{position[0]}|{position[1]}".encode(
                "utf-8")
        ).digest())
        return candidates[:2] or [origin]

    def _home_positions(self) -> list[tuple[int, int]]:
        groups = []
        for building in self.local_map["buildings"]:
            if building["building_type"] != "home":
                continue
            left, top, right, bottom = building["bounds"]
            positions = self._unique_walkable(
                (x, y)
                for y in range(top + 1, bottom)
                for x in range(left + 1, right)
            )
            positions.sort(key=lambda position: (
                -(abs(position[0] - building["door"]["x"])
                  + abs(position[1] - building["door"]["y"])),
                position[1], position[0],
            ))
            groups.append(positions)
        return self._interleave_position_groups(groups)

    def _positions_for_places(self, place_types) -> list[tuple[int, int]]:
        groups = []
        requested = set(place_types)
        for building in self.local_map["buildings"]:
            if building["building_type"] not in requested:
                continue
            left, top, right, bottom = building["bounds"]
            positions = self._unique_walkable(
                (x, y)
                for y in range(top + 1, bottom)
                for x in range(left + 1, right)
            )
            positions.sort(key=lambda position: (
                -(abs(position[0] - building["door"]["x"])
                  + abs(position[1] - building["door"]["y"])),
                position[1], position[0],
            ))
            groups.append(positions)
        for zone in self.local_map["zones"]:
            if zone["id"] not in requested:
                continue
            left, top, right, bottom = zone["bounds"]
            groups.append(self._unique_walkable(
                (x, y)
                for y in range(max(0, top), min(self.local_map["height"], bottom + 1))
                for x in range(max(0, left), min(self.local_map["width"], right + 1))
            ))
        return self._interleave_position_groups(groups)

    def _interleave_position_groups(
            self, groups: list[list[tuple[int, int]]]
    ) -> list[tuple[int, int]]:
        """Take one position per building before using its next interior tile."""
        result = []
        seen = set(self._static_positions)
        max_length = max((len(group) for group in groups), default=0)
        for index in range(max_length):
            for group in groups:
                if index >= len(group):
                    continue
                position = group[index]
                if position in seen:
                    continue
                seen.add(position)
                result.append(position)
        return result

    def _fallback_positions(self) -> list[tuple[int, int]]:
        hub = self.local_map.get("profile", {}).get("hub", {})
        center = (
            int(hub.get("x", self.local_map["width"] // 2)),
            int(hub.get("y", self.local_map["height"] // 2)),
        )
        positions = [
            (x, y)
            for y in range(self.local_map["height"])
            for x in range(self.local_map["width"])
            if self._is_walkable((x, y))
        ]
        positions.sort(key=lambda item: (
            abs(item[0] - center[0]) + abs(item[1] - center[1]),
            item[1], item[0],
        ))
        return self._unique_walkable(positions)

    def _unique_walkable(self, positions) -> list[tuple[int, int]]:
        unique = []
        seen = set(self._static_positions)
        for position in positions:
            if (position in seen or position not in self._reachable_cells
                    or not self._is_walkable(position)):
                continue
            seen.add(position)
            unique.append(position)
        return unique

    def _assign_target(self, candidates, assigned: set, index: int):
        for offset in range(len(candidates)):
            candidate = candidates[(index + offset) % len(candidates)]
            if (candidate not in assigned and candidate not in self._static_positions
                    and candidate in self._reachable_cells
                    and all(
                        abs(candidate[0] - other[0])
                        + abs(candidate[1] - other[1]) >= 2
                        for other in assigned)
                    and self._is_walkable(candidate)):
                assigned.add(candidate)
                return candidate
        for candidate in candidates:
            if (candidate in self._reachable_cells
                    and self._is_walkable(candidate)):
                return candidate
        return (19, 34)

    def _move_npcs_one_tick(self) -> None:
        ordered = sorted(self._npcs.values(), key=lambda item: item["id"])
        if ordered:
            rotation = self.turn % len(ordered)
            ordered = ordered[rotation:] + ordered[:rotation]
        blocked = self._static_positions | {
            (self.player["x"], self.player["y"])}
        for npc in ordered:
            self._advance_traveler_clock(npc)
        schedules = {
            npc["id"]: self._schedule_target(npc) for npc in ordered}
        stationary_ids = {
            npc["id"] for npc in ordered
            if (npc["x"], npc["y"]) == schedules[npc["id"]][0]
        }
        intents: dict[str, tuple[int, int]] = {}
        claims: dict[tuple[int, int], list[str]] = {}
        for npc in ordered:
            current = (npc["x"], npc["y"])
            target, activity = schedules[npc["id"]]
            npc["activity"] = activity
            desired = self._planned_step(npc, current, target, blocked)
            if desired == current or desired in blocked:
                continue
            intents[npc["id"]] = desired
            claims.setdefault(desired, []).append(npc["id"])

        priority = {npc["id"]: index for index, npc in enumerate(ordered)}
        winners = {
            min(contenders, key=lambda npc_id: priority[npc_id]): destination
            for destination, contenders in claims.items()
        }
        position_owner = {
            (npc["x"], npc["y"]): npc["id"]
            for npc in self._npcs.values()
        }
        moving = dict(winners)
        destinations = set(moving.values())
        changed = True
        while changed:
            changed = False
            for npc_id, destination in list(moving.items()):
                occupant_id = position_owner.get(destination)
                if occupant_id is None or occupant_id in moving:
                    continue
                if occupant_id not in stationary_ids:
                    continue
                npc = self._npcs[npc_id]
                origin = (npc["x"], npc["y"])
                if origin in destinations:
                    continue
                moving[occupant_id] = origin
                destinations.add(origin)
                changed = True

        changed = True
        while changed:
            changed = False
            for npc_id, destination in list(moving.items()):
                occupant_id = position_owner.get(destination)
                if occupant_id is not None and occupant_id not in moving:
                    del moving[npc_id]
                    changed = True

        for npc_id, destination in moving.items():
            npc = self._npcs[npc_id]
            npc["x"], npc["y"] = destination
            if npc["path"] and npc["path"][0] == destination:
                npc["path"].pop(0)

    def _planned_step(self, npc: dict, start: tuple[int, int],
                      target: tuple[int, int],
                      temporary_blocking: set[tuple[int, int]],
                      ) -> tuple[int, int]:
        if start == target:
            npc["path_target"] = target
            npc["path"] = []
            return start
        if (npc["path_target"] != target or not npc["path"]
                or not self._is_walkable(npc["path"][0])
                or npc["path"][0] in temporary_blocking):
            npc["path_target"] = target
            npc["path"] = self._find_path(
                start, target, temporary_blocking)
        return npc["path"][0] if npc["path"] else start

    def _settle_npcs_at_current_time(self) -> None:
        occupied = set(self._static_positions)
        for npc in sorted(self._npcs.values(), key=lambda item: item["id"]):
            target, _ = self._schedule_target(npc)
            if target in occupied:
                target = self._nearest_open(target, occupied)
            npc["x"], npc["y"] = target
            _, activity = self._schedule_target(npc)
            npc["activity"] = activity
            occupied.add(target)
            entity = next(
                item for item in self.local_map["entities"]
                if item["id"] == npc["id"])
            entity["x"], entity["y"] = target

    def _nearest_open(self, origin: tuple[int, int],
                      occupied: set[tuple[int, int]]) -> tuple[int, int]:
        queue = deque([origin])
        seen = {origin}
        while queue:
            current = queue.popleft()
            if current not in occupied and self._is_walkable(current):
                return current
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                neighbor = (current[0] + dx, current[1] + dy)
                if neighbor in seen or not self._is_walkable(neighbor):
                    continue
                seen.add(neighbor)
                queue.append(neighbor)
        return origin

    def _schedule_target(self, npc: dict) -> tuple[tuple[int, int], str]:
        if npc.get("travel_path"):
            path = npc["travel_path"]
            if npc["travel_mode"] == "loop":
                cycle = max(1, 2 * len(path) - 2)
                cursor = npc["travel_cursor"] % cycle
                index = cursor if cursor < len(path) else cycle - cursor
            else:
                index = min(
                    len(path) - 1,
                    int(npc["travel_progress"] / npc["travel_duration"]
                        * (len(path) - 1)),
                )
            return path[index], "traveling"
        if npc["kind"] == "wildlife":
            targets = (npc["home"], npc["work"], npc["midday"])
            phase = (self.turn // 12 + npc["schedule_offset"]) % len(targets)
            return targets[phase], "foraging"
        local_minute = (
            self.minute_of_day - npc.get("schedule_offset", 0)) % (24 * 60)
        if local_minute < 7 * 60:
            target, activity = npc["home"], "resting"
        elif local_minute < 8 * 60:
            target, activity = npc["work"], "commuting"
        elif local_minute < 12 * 60:
            target, activity = npc["work"], "working"
        elif local_minute < 14 * 60:
            target, activity = npc["midday"], "midday"
        elif local_minute < 18 * 60:
            target, activity = npc["work"], "working"
        elif local_minute < 19 * 60:
            target, activity = npc["home"], "going_home"
        else:
            target, activity = npc["home"], "resting"
        if (npc["x"], npc["y"]) != target:
            if activity == "resting":
                activity = "going_home"
            elif activity == "working":
                activity = "commuting"
        return target, activity

    @staticmethod
    def _advance_traveler_clock(npc: dict) -> None:
        if not npc.get("travel_path"):
            return
        if npc["travel_mode"] == "loop":
            cycle = max(1, 2 * len(npc["travel_path"]) - 2)
            npc["travel_cursor"] = (npc["travel_cursor"] + 1) % cycle
        elif npc["travel_mode"] == "world_progress":
            npc["travel_progress"] = min(
                npc["travel_duration"], npc["travel_progress"] + 1)

    @staticmethod
    def _schedule_offset(npc_id: str) -> int:
        digest = hashlib.sha256(f"schedule|{npc_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:2], "big") % 31 - 15

    def _find_path(self, start: tuple[int, int],
                   target: tuple[int, int],
                   occupied: set[tuple[int, int]] | None = None,
                   ) -> list[tuple[int, int]]:
        temporary_blocking = set(occupied or ())
        temporary_blocking.discard(target)
        temporary_blocking.discard(start)
        queue = deque([start])
        previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        while queue:
            current = queue.popleft()
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                neighbor = (current[0] + dx, current[1] + dy)
                if neighbor in previous or not self._is_walkable(neighbor):
                    continue
                if neighbor in temporary_blocking:
                    continue
                if neighbor in self._static_positions and neighbor != target:
                    continue
                previous[neighbor] = current
                if neighbor == target:
                    path = [neighbor]
                    while previous[path[-1]] != start:
                        parent = previous[path[-1]]
                        if parent is None:
                            return []
                        path.append(parent)
                    path.reverse()
                    return path
                queue.append(neighbor)
        return []

    def _is_walkable(self, position: tuple[int, int]) -> bool:
        x, y = position
        width = self.local_map["width"]
        height = self.local_map["height"]
        if x < 0 or y < 0 or x >= width or y >= height:
            return False
        tile = self.local_map["tiles"][y * width + x]
        return tile not in self.local_map["blocking_tiles"]

    def _in_bounds(self, position: tuple[int, int]) -> bool:
        return (
            0 <= position[0] < self.local_map["width"]
            and 0 <= position[1] < self.local_map["height"]
        )

    def _reachable_from_player_start(self) -> set[tuple[int, int]]:
        start = (
            self.local_map["player_start"]["x"],
            self.local_map["player_start"]["y"],
        )
        queue = deque([start])
        reached = {start}
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                neighbor = (x + dx, y + dy)
                if (neighbor in reached or neighbor in self._static_positions
                        or not self._is_walkable(neighbor)):
                    continue
                reached.add(neighbor)
                queue.append(neighbor)
        return reached

    @staticmethod
    def _period_name(hour: int) -> str:
        if hour < 6:
            return "深夜"
        if hour < 9:
            return "清晨"
        if hour < 12:
            return "上午"
        if hour < 14:
            return "正午"
        if hour < 18:
            return "下午"
        if hour < 21:
            return "傍晚"
        return "夜晚"
