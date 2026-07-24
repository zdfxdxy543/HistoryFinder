"""Deterministic overland trade routes between settlements."""

from __future__ import annotations

import heapq
import hashlib
from dataclasses import dataclass, field


IMPASSABLE_BIOMES = {"ocean", "lake"}
BIOME_COSTS = {
    "plains": 1.0,
    "grassland": 1.0,
    "river_valley": 0.9,
    "scrubland": 1.3,
    "forest": 1.6,
    "desert": 1.8,
    "tundra": 1.9,
    "highland": 2.1,
    "mountain": 3.8,
    "river": 2.4,
}

ROUTE_ABANDONMENT_YEARS = 5
TRADE_STALE_GRACE_YEARS = 8
ROAD_OVERGROWN_YEARS = 8
ROAD_RUINED_YEARS = 24


def road_segment_id(first: tuple[int, int],
                    second: tuple[int, int]) -> str:
    low, high = sorted((first, second))
    return f"road_{low[0]}_{low[1]}_{high[0]}_{high[1]}"


@dataclass
class RoadSegment:
    """One physical road edge shared by any number of trade routes."""

    id: str
    cell_a: tuple[int, int]
    cell_b: tuple[int, int]
    built_year: int
    last_used_year: int
    route_ids: list[str] = field(default_factory=list)
    traffic_volume: float = 0.0
    status: str = "active"
    condition: float = 1.0
    revision: int = 1
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "cell_a": list(self.cell_a),
            "cell_b": list(self.cell_b),
            "built_year": self.built_year,
            "last_used_year": self.last_used_year,
            "route_ids": list(self.route_ids),
            "traffic_volume": self.traffic_volume,
            "status": self.status,
            "condition": self.condition,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RoadSegment":
        return cls(
            id=str(data["id"]),
            cell_a=(int(data["cell_a"][0]), int(data["cell_a"][1])),
            cell_b=(int(data["cell_b"][0]), int(data["cell_b"][1])),
            built_year=int(data["built_year"]),
            last_used_year=int(data.get(
                "last_used_year", data["built_year"])),
            route_ids=[str(item) for item in data.get("route_ids", [])],
            traffic_volume=float(data.get("traffic_volume", 0.0)),
            status=str(data.get("status", "active")),
            condition=float(data.get("condition", 1.0)),
            revision=int(data.get("revision", 1)),
            schema_version=int(data.get("schema_version", 1)),
        )

    def attach_route(self, route_id: str, year: int,
                     active: bool = True) -> None:
        changed = False
        if route_id not in self.route_ids:
            self.route_ids.append(route_id)
            self.route_ids.sort()
            changed = True
        if active and self.status != "active":
            self.status = "active"
            self.condition = max(self.condition, 0.65)
            changed = True
        if active:
            self.last_used_year = max(self.last_used_year, year)
        if changed:
            self.revision += 1


@dataclass
class TradeRoute:
    id: str
    settlement_a_id: str
    settlement_b_id: str
    opened_year: int
    path: list[tuple[int, int]]
    opened_event_id: str = ""
    status: str = "active"
    segment_ids: list[str] = field(default_factory=list)
    last_active_year: int | None = None
    closed_year: int | None = None
    closure_reason: str = ""
    revision: int = 1
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.last_active_year is None:
            self.last_active_year = self.opened_year

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "settlement_a_id": self.settlement_a_id,
            "settlement_b_id": self.settlement_b_id,
            "opened_year": self.opened_year,
            "opened_event_id": self.opened_event_id,
            "status": self.status,
            "segment_ids": list(self.segment_ids),
            "last_active_year": self.last_active_year,
            "closed_year": self.closed_year,
            "closure_reason": self.closure_reason,
            "revision": self.revision,
            "path": [[x, y] for x, y in self.path],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TradeRoute":
        status = str(data.get("status", "active"))
        if status == "destroyed":
            status = "abandoned"
        return cls(
            id=str(data["id"]),
            settlement_a_id=str(data["settlement_a_id"]),
            settlement_b_id=str(data["settlement_b_id"]),
            opened_year=int(data["opened_year"]),
            opened_event_id=str(data.get("opened_event_id", "")),
            status=status,
            segment_ids=[str(item) for item in data.get("segment_ids", [])],
            last_active_year=int(data.get(
                "last_active_year", data["opened_year"])),
            closed_year=(None if data.get("closed_year") is None
                         else int(data["closed_year"])),
            closure_reason=str(data.get("closure_reason", "")),
            revision=int(data.get("revision", 1)),
            path=[(int(item[0]), int(item[1])) for item in data["path"]],
            schema_version=2,
        )


@dataclass
class TravelGroup:
    """A persistent road party moving between a trade route's endpoints."""

    id: str
    route_id: str
    origin_settlement_id: str
    destination_settlement_id: str
    path_index: int = 0
    direction: int = 1
    progress_minutes: int = 0
    status: str = "traveling"
    cargo: list[str] = None
    guard_count: int = 2
    group_type: str = "caravan"
    traveler_role: str = ""
    dialogue_variant: int = 0
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.cargo is None:
            self.cargo = []

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "route_id": self.route_id,
            "origin_settlement_id": self.origin_settlement_id,
            "destination_settlement_id": self.destination_settlement_id,
            "path_index": self.path_index,
            "direction": self.direction,
            "progress_minutes": self.progress_minutes,
            "status": self.status,
            "cargo": list(self.cargo),
            "guard_count": self.guard_count,
            "group_type": self.group_type,
            "traveler_role": self.traveler_role,
            "dialogue_variant": self.dialogue_variant,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TravelGroup":
        return cls(
            id=str(data["id"]),
            route_id=str(data["route_id"]),
            origin_settlement_id=str(data["origin_settlement_id"]),
            destination_settlement_id=str(data["destination_settlement_id"]),
            path_index=int(data.get("path_index", 0)),
            direction=int(data.get("direction", 1)),
            progress_minutes=int(data.get("progress_minutes", 0)),
            status=str(data.get("status", "traveling")),
            cargo=[str(item) for item in data.get("cargo", [])],
            guard_count=int(data.get("guard_count", 2)),
            group_type=str(data.get("group_type", "caravan")),
            traveler_role=str(data.get("traveler_role", "")),
            dialogue_variant=int(data.get("dialogue_variant", 0)),
            schema_version=2,
        )

    def current_cell(self, route: TradeRoute) -> tuple[int, int]:
        index = max(0, min(len(route.path) - 1, self.path_index))
        return route.path[index]

    def advance(self, minutes: int, route: TradeRoute) -> None:
        if minutes <= 0 or len(route.path) < 2 or route.status != "active":
            return
        self.progress_minutes += minutes
        minutes_per_cell = 180
        while self.progress_minutes >= minutes_per_cell:
            self.progress_minutes -= minutes_per_cell
            next_index = self.path_index + self.direction
            if next_index >= len(route.path):
                self.direction = -1
                next_index = len(route.path) - 2
                self.origin_settlement_id, self.destination_settlement_id = (
                    self.destination_settlement_id,
                    self.origin_settlement_id,
                )
            elif next_index < 0:
                self.direction = 1
                next_index = 1
                self.origin_settlement_id, self.destination_settlement_id = (
                    self.destination_settlement_id,
                    self.origin_settlement_id,
                )
            self.path_index = next_index
        destination_index = (
            len(route.path) - 1 if self.direction > 0 else 0)
        self.status = (
            "arrived" if self.path_index == destination_index
            else "traveling")


def caravan_id(route_key: str) -> str:
    return f"caravan_{route_key.removeprefix('route_')}"


def traveler_id(route_key: str, index: int) -> str:
    return f"traveler_{route_key.removeprefix('route_')}_{index}"


def stable_route_int(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(
        "|".join(parts).encode("utf-8")).digest()[:8], "big")


def route_id(settlement_a_id: str, settlement_b_id: str) -> str:
    first, second = sorted((settlement_a_id, settlement_b_id))
    return f"route_{first}_{second}"


class RoutePlanner:
    """A stable four-neighbor A* planner over the generated world grid."""

    def plan(self, world, start: tuple[int, int],
             goal: tuple[int, int]) -> list[tuple[int, int]]:
        if start == goal:
            return [start]
        geography = world.geography
        existing = {
            cell for route in world.trade_routes.values()
            if route.status == "active" for cell in route.path
        }
        frontier: list[tuple[float, float, int, int]] = []
        heapq.heappush(frontier, (self._heuristic(start, goal), 0.0,
                                  start[1], start[0]))
        previous: dict[tuple[int, int], tuple[int, int] | None] = {
            start: None}
        costs = {start: 0.0}

        while frontier:
            _, current_cost, y, x = heapq.heappop(frontier)
            current = (x, y)
            if current_cost != costs.get(current):
                continue
            if current == goal:
                return self._reconstruct(previous, goal)
            for neighbor in self._neighbors(x, y, geography.width,
                                            geography.height):
                if neighbor != goal and neighbor != start:
                    biome = str(geography.biomes[neighbor[1], neighbor[0]])
                    if biome in IMPASSABLE_BIOMES:
                        continue
                step_cost = self._cell_cost(geography, neighbor)
                if neighbor in existing:
                    step_cost *= 0.62
                new_cost = current_cost + step_cost
                if new_cost >= costs.get(neighbor, float("inf")):
                    continue
                costs[neighbor] = new_cost
                previous[neighbor] = current
                priority = new_cost + self._heuristic(neighbor, goal)
                heapq.heappush(frontier, (
                    priority, new_cost, neighbor[1], neighbor[0]))
        return []

    @staticmethod
    def _neighbors(x: int, y: int, width: int,
                   height: int) -> list[tuple[int, int]]:
        return [
            (nx, ny) for nx, ny in (
                (x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1))
            if 0 <= nx < width and 0 <= ny < height
        ]

    @staticmethod
    def _heuristic(first: tuple[int, int], second: tuple[int, int]) -> float:
        return float(abs(first[0] - second[0]) + abs(first[1] - second[1]))

    @staticmethod
    def _cell_cost(geography, cell: tuple[int, int]) -> float:
        x, y = cell
        biome = str(geography.biomes[y, x])
        base = BIOME_COSTS.get(biome, 1.5)
        slope = 0.0
        elevation = float(geography.heightmap[y, x])
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < geography.width and 0 <= ny < geography.height:
                slope = max(slope, abs(
                    elevation - float(geography.heightmap[ny, nx])))
        return base + slope * 8.0

    @staticmethod
    def _reconstruct(previous, goal: tuple[int, int]) -> list[tuple[int, int]]:
        path = [goal]
        while previous[path[-1]] is not None:
            path.append(previous[path[-1]])
        path.reverse()
        return path
