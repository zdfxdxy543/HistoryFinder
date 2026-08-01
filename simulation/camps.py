"""Persistent wilderness camps and their short-lived material traces."""

from __future__ import annotations

from dataclasses import dataclass


CAMP_EMBERS_MINUTES = 120
CAMP_WEATHERED_MINUTES = 7 * 24 * 60
CAMP_ERASED_MINUTES = 21 * 24 * 60


@dataclass
class WildernessCamp:
    id: str
    world_cell: tuple[int, int]
    camp_type: str
    state: str
    layout_seed: int
    established_minute: int
    state_changed_minute: int
    last_occupied_minute: int
    owner_group_id: str = ""
    revision: int = 1
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "world_cell": list(self.world_cell),
            "camp_type": self.camp_type,
            "state": self.state,
            "layout_seed": self.layout_seed,
            "established_minute": self.established_minute,
            "state_changed_minute": self.state_changed_minute,
            "last_occupied_minute": self.last_occupied_minute,
            "owner_group_id": self.owner_group_id,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WildernessCamp":
        cell = data["world_cell"]
        return cls(
            id=str(data["id"]),
            world_cell=(int(cell[0]), int(cell[1])),
            camp_type=str(data.get("camp_type", "caravan")),
            state=str(data.get("state", "weathered")),
            layout_seed=int(data.get("layout_seed", 0)),
            established_minute=int(data.get("established_minute", 0)),
            state_changed_minute=int(data.get("state_changed_minute", 0)),
            last_occupied_minute=int(data.get("last_occupied_minute", 0)),
            owner_group_id=str(data.get("owner_group_id", "")),
            revision=int(data.get("revision", 1)),
            schema_version=1,
        )

    def occupy(self, minute: int, owner_group_id: str) -> None:
        changed = self.state != "occupied" or self.owner_group_id != owner_group_id
        self.state = "occupied"
        self.owner_group_id = owner_group_id
        self.last_occupied_minute = minute
        if changed:
            self.state_changed_minute = minute
            self.revision += 1

    def vacate(self, minute: int) -> None:
        if self.state != "occupied":
            return
        self.state = "embers"
        self.owner_group_id = ""
        self.last_occupied_minute = minute
        self.state_changed_minute = minute
        self.revision += 1

    def weather_to(self, minute: int) -> bool:
        if self.state in {"occupied", "erased"}:
            return False
        age = max(0, minute - self.state_changed_minute)
        target = self.state
        if self.state == "embers" and age >= CAMP_EMBERS_MINUTES:
            target = "abandoned"
        elif self.state == "abandoned" and age >= CAMP_WEATHERED_MINUTES:
            target = "weathered"
        elif self.state == "weathered" and age >= CAMP_ERASED_MINUTES:
            target = "erased"
        if target == self.state:
            return False
        self.state = target
        self.state_changed_minute = minute
        self.revision += 1
        return True


def camp_id(group_id: str, established_minute: int) -> str:
    return f"camp_{group_id}_{established_minute}"
