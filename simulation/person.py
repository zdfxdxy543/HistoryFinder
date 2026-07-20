"""Persistent notable people used by political and military history."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from simulation.names import generate_name


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
    schema_version: int = 1

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
