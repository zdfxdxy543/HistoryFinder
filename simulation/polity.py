"""Political entities and time-bounded settlement control."""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulation.names import generate_unique_name


@dataclass
class Polity:
    """A political authority that may control multiple settlements."""

    id: str
    name: str
    founded_year: int
    capital_settlement_id: str
    ruler_id: str | None = None
    dissolved_year: int | None = None
    alive: bool = True
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "founded_year": self.founded_year,
            "capital_settlement_id": self.capital_settlement_id,
            "ruler_id": self.ruler_id,
            "dissolved_year": self.dissolved_year,
            "alive": self.alive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Polity":
        return cls(
            id=data["id"],
            name=data["name"],
            founded_year=int(data["founded_year"]),
            capital_settlement_id=data["capital_settlement_id"],
            ruler_id=data["ruler_id"],
            dissolved_year=data["dissolved_year"],
            alive=bool(data["alive"]),
            schema_version=int(data["schema_version"]),
        )


@dataclass
class SettlementControlPeriod:
    """A half-open [start_year, end_year) political-control interval."""

    id: str
    settlement_id: str
    polity_id: str
    start_year: int
    end_year: int | None = None
    reason: str = "founding"
    event_id: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "settlement_id": self.settlement_id,
            "polity_id": self.polity_id,
            "start_year": self.start_year,
            "end_year": self.end_year,
            "reason": self.reason,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SettlementControlPeriod":
        return cls(
            id=data["id"],
            settlement_id=data["settlement_id"],
            polity_id=data["polity_id"],
            start_year=int(data["start_year"]),
            end_year=(None if data["end_year"] is None
                      else int(data["end_year"])),
            reason=data["reason"],
            event_id=data["event_id"],
            schema_version=int(data["schema_version"]),
        )


class PolityManager:
    """Create deterministic political entities and control periods."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed + 730)
        self.polity_counter = 0
        self.control_counter = 0
        self.used_names: set[str] = set()

    def create_polity(self, capital_settlement_id: str, ruler_id: str | None,
                      year: int) -> Polity:
        self.polity_counter += 1
        name = generate_unique_name(
            self.rng.randint(0, 100000), self.used_names, "kingdom")
        return Polity(
            id=f"polity_{self.polity_counter:04d}",
            name=name,
            founded_year=year,
            capital_settlement_id=capital_settlement_id,
            ruler_id=ruler_id,
        )

    def create_control_period(self, settlement_id: str, polity_id: str,
                              year: int, reason: str,
                              event_id: str | None = None,
                              ) -> SettlementControlPeriod:
        control_id = self.reserve_control_id()
        return SettlementControlPeriod(
            id=control_id,
            settlement_id=settlement_id,
            polity_id=polity_id,
            start_year=year,
            reason=reason,
            event_id=event_id,
        )

    def reserve_control_id(self) -> str:
        self.control_counter += 1
        return f"control_{self.control_counter:06d}"

    def restore_counters(
            self, polities: dict[str, Polity],
            control_periods: dict[str, SettlementControlPeriod]) -> None:
        self.polity_counter = _max_numeric_suffix(polities, "polity_")
        self.control_counter = _max_numeric_suffix(
            control_periods, "control_")
        self.used_names = {polity.name for polity in polities.values()}


def _max_numeric_suffix(values, prefix: str) -> int:
    maximum = 0
    for value in values:
        if not value.startswith(prefix):
            continue
        suffix = value[len(prefix):]
        if suffix.isdigit():
            maximum = max(maximum, int(suffix))
    return maximum
