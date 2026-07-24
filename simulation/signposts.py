"""Persistent signposts and frozen sign-board text."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace


def stable_signpost_int(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def misspell_text(text: str, seed: int) -> str:
    if not text:
        return text
    replacements = "安北河山林石新古东南西门镇城"
    index = seed % len(text)
    replacement = replacements[(seed // 17) % len(replacements)]
    if replacement == text[index]:
        replacement = replacements[(seed // 17 + 1) % len(replacements)]
    return text[:index] + replacement + text[index + 1:]


def drop_text_character(text: str, seed: int) -> str:
    if not text:
        return text
    index = seed % len(text)
    return text[:index] + "□" + text[index + 1:]


def obscure_text_character(text: str, seed: int) -> str:
    if not text:
        return text
    index = seed % len(text)
    return text[:index] + "？" + text[index + 1:]


@dataclass
class SignBoard:
    id: str
    destination_id: str
    displayed_name: str
    displayed_distance: str
    direction: str
    written_year: int
    writer_person_id: str = ""
    source_route_id: str = ""
    legibility: str = "clear"
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "destination_id": self.destination_id,
            "displayed_name": self.displayed_name,
            "displayed_distance": self.displayed_distance,
            "direction": self.direction,
            "written_year": self.written_year,
            "writer_person_id": self.writer_person_id,
            "source_route_id": self.source_route_id,
            "legibility": self.legibility,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignBoard":
        return cls(
            id=str(data["id"]),
            destination_id=str(data["destination_id"]),
            displayed_name=str(data["displayed_name"]),
            displayed_distance=str(data["displayed_distance"]),
            direction=str(data["direction"]),
            written_year=int(data["written_year"]),
            writer_person_id=str(data.get("writer_person_id", "")),
            source_route_id=str(data.get("source_route_id", "")),
            legibility=str(data.get("legibility", "clear")),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class SignRepair:
    year: int
    board_id: str
    repairer_person_id: str
    repair_type: str
    error_type: str = "none"
    event_id: str = ""

    def to_dict(self) -> dict:
        return {
            "year": self.year,
            "board_id": self.board_id,
            "repairer_person_id": self.repairer_person_id,
            "repair_type": self.repair_type,
            "error_type": self.error_type,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SignRepair":
        return cls(
            year=int(data["year"]),
            board_id=str(data["board_id"]),
            repairer_person_id=str(data.get("repairer_person_id", "")),
            repair_type=str(data["repair_type"]),
            error_type=str(data.get("error_type", "none")),
            event_id=str(data.get("event_id", "")),
        )


@dataclass
class Signpost:
    id: str
    world_cell: tuple[int, int]
    built_year: int
    builder_settlement_id: str
    route_ids: list[str] = field(default_factory=list)
    original_boards: list[SignBoard] = field(default_factory=list)
    current_boards: list[SignBoard] = field(default_factory=list)
    condition: str = "sound"
    wear_level: str = "light"
    repair_history: list[SignRepair] = field(default_factory=list)
    abandoned_year: int | None = None
    revision: int = 1
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "world_cell": list(self.world_cell),
            "built_year": self.built_year,
            "builder_settlement_id": self.builder_settlement_id,
            "route_ids": list(self.route_ids),
            "original_boards": [item.to_dict() for item in self.original_boards],
            "current_boards": [item.to_dict() for item in self.current_boards],
            "condition": self.condition,
            "wear_level": self.wear_level,
            "repair_history": [item.to_dict() for item in self.repair_history],
            "abandoned_year": self.abandoned_year,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Signpost":
        return cls(
            id=str(data["id"]),
            world_cell=(int(data["world_cell"][0]), int(data["world_cell"][1])),
            built_year=int(data["built_year"]),
            builder_settlement_id=str(data["builder_settlement_id"]),
            route_ids=[str(item) for item in data.get("route_ids", [])],
            original_boards=[SignBoard.from_dict(item)
                             for item in data.get("original_boards", [])],
            current_boards=[SignBoard.from_dict(item)
                            for item in data.get("current_boards", [])],
            condition=str(data.get("condition", "sound")),
            wear_level=str(data.get("wear_level", "light")),
            repair_history=[SignRepair.from_dict(item)
                            for item in data.get("repair_history", [])],
            abandoned_year=(None if data.get("abandoned_year") is None
                            else int(data["abandoned_year"])),
            revision=int(data.get("revision", 1)),
            schema_version=int(data.get("schema_version", 1)),
        )

    def add_boards(self, route_id: str, boards: list[SignBoard]) -> None:
        changed = False
        if route_id not in self.route_ids:
            self.route_ids.append(route_id)
            self.route_ids.sort()
            changed = True
        existing = {(item.destination_id, item.source_route_id)
                    for item in self.original_boards}
        for board in boards:
            key = (board.destination_id, board.source_route_id)
            if key in existing:
                continue
            self.original_boards.append(board)
            self.current_boards.append(replace(board))
            existing.add(key)
            changed = True
        if changed:
            self.abandoned_year = None
            self.revision += 1

    def weather_to(self, year: int, seed: int) -> None:
        age = max(0, year - self.built_year)
        wear = "heavy" if age >= 24 else "moderate" if age >= 9 else "light"
        condition = "abandoned" if self.abandoned_year is not None else (
            "damaged" if wear == "heavy" else
            "weathered" if wear == "moderate" else "sound")
        if wear == self.wear_level and condition == self.condition:
            return
        self.wear_level = wear
        self.condition = condition
        if self.current_boards and wear in {"moderate", "heavy"}:
            roll = stable_signpost_int(str(seed), self.id, wear)
            target = roll % len(self.current_boards)
            board = self.current_boards[target]
            if board.legibility == "clear":
                if wear == "moderate":
                    board.displayed_name = obscure_text_character(
                        board.displayed_name, roll // 17)
                    board.legibility = "weathered"
                else:
                    board.displayed_distance = drop_text_character(
                        board.displayed_distance, roll // 17)
                    board.legibility = "damaged"
        self.revision += 1

    def repair(self, board_id: str, year: int, repairer_person_id: str,
               seed: int, event_id: str = "", repair_type: str | None = None,
               error_type: str | None = None) -> SignRepair:
        original = next(item for item in self.original_boards
                        if item.id == board_id)
        index = next(index for index, item in enumerate(self.current_boards)
                     if item.id == board_id)
        roll = stable_signpost_int(str(seed), self.id, board_id, str(year),
                                   repairer_person_id)
        repair_types = ("iron_strap", "replacement_board", "rope_binding",
                        "fresh_paint")
        repair_type = repair_type or repair_types[roll % len(repair_types)]
        errors = ("misspelling", "distance_error", "missing_character",
                  "illegible_text", "illegible_distance", "none", "none",
                  "none", "none", "none")
        error_type = error_type or errors[(roll // 13) % len(errors)]
        board = replace(original, written_year=year,
                        writer_person_id=repairer_person_id)
        if error_type == "misspelling":
            board.displayed_name = misspell_text(board.displayed_name, roll // 31)
        elif error_type == "distance_error":
            offset = (-2, -1, 1, 2)[(roll // 31) % 4]
            board.displayed_distance = str(max(
                1, int(board.displayed_distance) + offset))
        elif error_type == "missing_character":
            if (roll // 47) % 3 == 0:
                board.displayed_distance = drop_text_character(
                    board.displayed_distance, roll // 61)
            else:
                board.displayed_name = drop_text_character(
                    board.displayed_name, roll // 61)
            board.legibility = "damaged"
        elif error_type == "illegible_text":
            board.displayed_name = obscure_text_character(
                board.displayed_name, roll // 61)
            board.legibility = "weathered"
        elif error_type == "illegible_distance":
            board.displayed_distance = obscure_text_character(
                board.displayed_distance, roll // 61)
            board.legibility = "weathered"
        self.current_boards[index] = board
        record = SignRepair(year, board_id, repairer_person_id, repair_type,
                            error_type, event_id)
        self.repair_history.append(record)
        self.condition = "repaired"
        self.revision += 1
        return record
