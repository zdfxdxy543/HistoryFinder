"""Turn-based local time, movement, and deterministic NPC schedules."""

from __future__ import annotations

import hashlib
from collections import deque


ACTIVITY_NAMES = {
    "commuting": "正在上工",
    "working": "正在工作",
    "midday": "正在午间外出",
    "going_home": "正在回家",
    "resting": "正在家中休息",
}


WORKPLACE_TYPES = {
    "scholar": ("archive", "academy"),
    "scribe": ("archive", "hall"),
    "elder": ("hall",),
    "merchant": ("market",),
    "artisan": ("workshop",),
    "farmer": ("field", "mill"),
    "weaver": ("workshop",),
    "porter": ("market", "dock", "granary"),
    "baker": ("bakery",),
    "vendor": ("market",),
    "water_carrier": ("cistern", "well", "market"),
    "carpenter": ("workshop", "lumberyard"),
    "inn_worker": ("inn",),
    "laborer": ("granary", "quarry", "lumberyard", "dock"),
}


BREAK_PLACE_TYPES = (
    "market", "well", "inn", "hall", "temple", "academy", "dock",
)


class LocalTimeSimulation:
    """Authoritative local clock and movement state for one player session."""

    tick_minutes = 1

    def __init__(self, local_map: dict, day: int = 1,
                 minute_of_day: int = 6 * 60 + 55,
                 settle_npcs: bool = False):
        self.local_map = local_map
        self.day = max(1, day)
        self.minute_of_day = minute_of_day % (24 * 60)
        self.turn = 0
        self.player = dict(local_map["player_start"])
        self._static_positions = {
            (item["x"], item["y"])
            for item in local_map["entities"]
            if (item["kind"] in {"evidence", "container"}
                and item.get("blocks_movement", True))
        }
        self._reachable_cells = self._reachable_from_player_start()
        self._npcs: dict[str, dict] = {}
        self._initialize_npcs()
        if settle_npcs:
            self._settle_npcs_at_current_time()

    def move_player(self, dx: int, dy: int) -> dict:
        if abs(dx) + abs(dy) != 1:
            raise ValueError("移动必须是相邻的一个格子。")
        target = (self.player["x"] + dx, self.player["y"] + dy)
        occupied = {
            (npc["x"], npc["y"]) for npc in self._npcs.values()}
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
        return {
            "day": self.day,
            "minute_of_day": self.minute_of_day,
            "time_label": f"{hour:02d}:{minute:02d}",
            "period_name": self._period_name(hour),
            "turn": self.turn,
            "player": dict(self.player),
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
            if item["kind"] in {"informant", "resident"}
        ]
        for index, entity in enumerate(sorted(npcs, key=lambda item: item["id"])):
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
                "activity": "resting",
                "path_target": None,
                "path": [],
            }

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
