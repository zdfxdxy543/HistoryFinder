"""Persistent notable people used by political and military history."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from simulation.names import generate_name


TRAVEL_ROLE_NAMES = {
    "merchant": "商旅",
    "visiting_scholar": "访问学者",
    "envoy": "使者",
    "refugee": "流民",
    "captive": "俘虏",
    "survivor": "废墟幸存者",
    "disaster_casualty": "灾难死者",
}

HIDDEN_TRAVEL_ROLES = {"thief", "smuggler", "fugitive", "spy"}


def public_travel_role(person) -> str:
    """Return only a role that the person presents openly in public."""
    if person.travel_role in HIDDEN_TRAVEL_ROLES:
        return ""
    return TRAVEL_ROLE_NAMES.get(person.travel_role, "")


def public_mobility_status(person) -> str:
    """Collapse simulation-only movement states into observable categories."""
    if person.mobility_status == "resident":
        return "resident"
    if person.mobility_status == "ruin_survivor":
        return "survivor"
    if person.travel_role == "captive":
        return "captive"
    return "visitor"


@dataclass
class Person:
    id: str
    name: str
    birth_year: int
    settlement_id: str
    alive: bool = True
    death_year: int | None = None
    roles: list[str] = field(default_factory=list)
    parent_ids: list[str] = field(default_factory=list)
    spouse_ids: list[str] = field(default_factory=list)
    current_location_id: str = ""
    mobility_status: str = "resident"
    travel_role: str = ""
    stay_until_year: int | None = None
    carried_evidence_ids: list[str] = field(default_factory=list)
    movement_history: list[dict] = field(default_factory=list)
    schema_version: int = 2

    def __post_init__(self) -> None:
        if not self.current_location_id:
            self.current_location_id = self.settlement_id

    def age_at(self, year: int) -> int:
        return max(0, year - self.birth_year)

    def add_role(self, role: str) -> None:
        if role not in self.roles:
            self.roles.append(role)

    def remove_role(self, role: str) -> None:
        if role in self.roles:
            self.roles.remove(role)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "birth_year": self.birth_year,
            "settlement_id": self.settlement_id,
            "alive": self.alive,
            "death_year": self.death_year,
            "roles": list(self.roles),
            "parent_ids": list(self.parent_ids),
            "spouse_ids": list(self.spouse_ids),
            "current_location_id": self.current_location_id,
            "mobility_status": self.mobility_status,
            "travel_role": self.travel_role,
            "stay_until_year": self.stay_until_year,
            "carried_evidence_ids": list(self.carried_evidence_ids),
            "movement_history": [dict(item) for item in self.movement_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Person":
        return cls(
            id=data["id"],
            name=data["name"],
            birth_year=data["birth_year"],
            settlement_id=data["settlement_id"],
            alive=data.get("alive", True),
            death_year=data.get("death_year"),
            roles=list(data.get("roles", [])),
            parent_ids=list(data.get("parent_ids", [])),
            spouse_ids=list(data.get("spouse_ids", [])),
            current_location_id=data.get(
                "current_location_id", data["settlement_id"]),
            mobility_status=data.get("mobility_status", "resident"),
            travel_role=data.get("travel_role", ""),
            stay_until_year=data.get("stay_until_year"),
            carried_evidence_ids=list(data.get("carried_evidence_ids", [])),
            movement_history=[
                dict(item) for item in data.get("movement_history", [])],
            schema_version=data.get("schema_version", 1),
        )


class PersonManager:
    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed + 810)
        self.counter = 0

    def create_person(self, settlement_id: str, birth_year: int,
                      roles: list[str] | None = None,
                      name: str | None = None,
                      parent_ids: list[str] | None = None) -> Person:
        self.counter += 1
        return Person(
            id=f"person_{self.counter:04d}",
            name=name or generate_name(self.rng.randint(0, 100000), "ruler"),
            birth_year=birth_year,
            settlement_id=settlement_id,
            roles=list(roles or []),
            parent_ids=list(parent_ids or []),
        )

    def should_die(self, person: Person, year: int) -> bool:
        age = person.age_at(year)
        if age < 45:
            probability = 0.001
        elif age < 55:
            probability = 0.006
        elif age < 65:
            probability = 0.020
        elif age < 75:
            probability = 0.060
        elif age < 85:
            probability = 0.150
        else:
            probability = 0.350
        roll = random.Random(
            f"{self.seed}|mortality|{person.id}|{year}").random()
        return roll < probability
