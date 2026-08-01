"""Truth-isolated state and actions for the browser play prototype."""

from __future__ import annotations

import copy
import math

from game.comparison import ComparisonEngine
from game.consultation import ConsultationEngine
from game.investigation import (
    ConsultantView,
    DocumentReading,
    EvidencePublicView,
    HeldKnowledgeView,
    ReadingPublicView,
    RecordPublicView,
    build_reading_statements,
)
from game.knowledge import PlayerKnowledge
from game.local_map import build_evidence_targets
from game.local_time import LocalTimeSimulation
from game.world_cell_map import (
    LocalMapRepository,
    cell_key,
    decorate_travel_groups,
)
from simulation.person import (
    HIDDEN_TRAVEL_ROLES,
    public_mobility_status,
    public_travel_role,
)
from simulation.territory import build_territory_payload
from game.observation import build_evidence_observations
from narrative.context_builder import build_evidence_context
from narrative.document_reader import (
    is_public_inscription,
    preview_public_inscription,
    read_document,
)
from narrative.evidence_describer import describe_at_glance, describe_evidence
from simulation.text_carriers import (
    has_text_carrier,
    materialize_text_carrier,
)


ROLE_NAMES = {
    "scholar": "学者",
    "scribe": "书记",
    "elder": "地方长者",
    "merchant": "商人",
    "artisan": "工匠",
    "priest": "仪式保管人",
}


ACCESS_NOTES = {
    "public": "这里可以直接进行调查。",
    "supervised": "保管人员在旁见证了这次查验。",
    "permission": "说明调查目的后，管理者允许你在场查验。",
    "restricted": "登记身份和调查理由后，你获得了一次受监督的查阅机会。",
    "private": "保管者同意打开箱柜，但要求所有物品留在原处。",
    "buried": "这处地点需要逐层清理和记录。",
}

PLAYER_BIOME_CODES = {
    "mountain": 0, "highland": 1, "river_valley": 2, "forest": 3,
    "desert": 4, "grassland": 5, "tundra": 6, "scrubland": 7,
    "plains": 8, "ocean": 9, "lake": 10, "river": 11,
}

FIRST_CHEAT_CODE = "HF-VISION"


class PlayerActionError(ValueError):
    pass


class PlayerSession:
    """One local player state that never serializes simulation truth."""

    def __init__(self, world, settlement_id: str | None = None):
        self.world = world
        self.knowledge = PlayerKnowledge()
        self.known_languages = {"common"}
        self._consultation_engine = ConsultationEngine()
        self._comparison_engine = ComparisonEngine()
        self._unlocked_cheats: set[str] = set()
        self.full_map_vision = False
        self._explored_by_cell: dict[str, set[tuple[int, int]]] = {}
        self.current_location_id = settlement_id or self._starting_settlement_id()
        settlement = self.world.settlements[self.current_location_id]
        self.current_cell = (int(settlement.grid_x), int(settlement.grid_y))
        self._map_repository = LocalMapRepository(self.world)
        self.local_map = self._map_repository.get(*self.current_cell)
        decorate_travel_groups(self.local_map, self.world)
        self._decorate_local_map_evidence()
        self.local_time = LocalTimeSimulation(
            self.local_map,
            world_seed=self.world.seed,
            location_id=cell_key(*self.current_cell),
            biome=str(settlement.biome),
        )

    def bootstrap(self) -> dict:
        settlement = self.world.settlements[self.current_location_id]
        return {
            "schema_version": 1,
            "mode": "player_safe",
            "world": {
                "seed": self.world.seed,
                "name": self.world.name,
                "current_year": self.world.current_year,
            },
            "settlement": {
                "id": settlement.id,
                "name": settlement.name,
                "size": settlement.size,
                "biome": settlement.biome,
                "population": settlement.population,
                "alive": settlement.alive,
            },
            "local_map": self.local_map,
            "runtime": self.local_time.snapshot(),
            "world_map": self._world_map_payload(),
            "informants": self._informants_payload(),
            "journal": self.journal_payload(),
            "cheats": self._cheats_payload(),
        }

    def enter_cheat_code(self, code: str) -> dict:
        if code.strip().upper() != FIRST_CHEAT_CODE:
            raise PlayerActionError("作弊码无效。")
        self._unlocked_cheats.add("full_map_vision")
        return {
            "action": "enter_cheat",
            "cheats": self._cheats_payload(),
            "runtime": self.local_time.snapshot(),
        }

    def set_cheat(self, cheat_id: str, enabled: bool) -> dict:
        if cheat_id != "full_map_vision":
            raise PlayerActionError("无法识别这个作弊选项。")
        if cheat_id not in self._unlocked_cheats:
            raise PlayerActionError("这个作弊选项尚未解锁。")
        self.full_map_vision = bool(enabled)
        self.local_time.full_map_vision = self.full_map_vision
        return {
            "action": "set_cheat",
            "cheats": self._cheats_payload(),
            "runtime": self.local_time.snapshot(),
        }

    def _cheats_payload(self) -> dict:
        return {
            "full_map_vision": {
                "unlocked": "full_map_vision" in self._unlocked_cheats,
                "enabled": self.full_map_vision,
            },
        }

    def examine(self, evidence_id: str) -> dict:
        evidence = self.world.evidence.get(evidence_id)
        if evidence is None:
            raise PlayerActionError("这里找不到这件证物。")
        newly_discovered = evidence_id not in \
            self.knowledge.discovered_evidence_ids
        if newly_discovered:
            marker = next(
                (item for item in self.local_map["entities"]
                 if item["kind"] == "evidence" and item["id"] == evidence_id),
                None,
            )
            if (marker is None
                    or evidence.location_id != self._active_location_id()
                    or evidence.state == "destroyed"
                    or evidence.evidence_type == "oral"):
                raise PlayerActionError("这里找不到这件证物。")
            distance = (
                abs(marker["x"] - self.local_time.player["x"])
                + abs(marker["y"] - self.local_time.player["y"])
            )
            if distance > 1:
                raise PlayerActionError("需要先走到这件证物旁边。")
            self.knowledge.discover_evidence(evidence.id)
            self._sync_discovered_evidence()
        else:
            evidence = self._local_evidence(evidence_id)
        view = EvidencePublicView.from_evidence(evidence)
        observations = build_evidence_observations(view)
        added = self.knowledge.record_observations(evidence.id, observations)
        return self._finish_action({
            "action": "examine",
            "evidence": self._evidence_payload(evidence),
            "description_cn": describe_evidence(build_evidence_context(evidence)),
            "observations": [item.to_dict() for item in observations],
            "new_observation_count": added,
            "newly_discovered": newly_discovered,
            "local_map": self.local_map,
            "journal": self.journal_payload(),
        }, 15)

    def search_container(self, container_id: str) -> dict:
        container = next(
            (item for item in self.local_map["entities"]
             if item["kind"] == "container" and item["id"] == container_id),
            None,
        )
        if container is None:
            raise PlayerActionError("这里找不到这个调查地点。")
        distance = (
            abs(container["x"] - self.local_time.player["x"])
            + abs(container["y"] - self.local_time.player["y"])
        )
        if distance > 1:
            raise PlayerActionError("需要先走到调查地点旁边。")

        target = next(
            (item for item in build_evidence_targets(
                self.world.evidence.values(), self.world.storage_sites,
                self._active_location_id())
             if item["id"] == container_id),
            None,
        )
        if target is None or target["kind"] != "container":
            raise PlayerActionError("这里找不到这个调查地点。")
        evidence = [
            self.world.evidence[evidence_id]
            for evidence_id in target["evidence_ids"]
        ]
        before = set(self.knowledge.discovered_evidence_ids)
        for item in evidence:
            self.knowledge.discover_evidence(item.id)
        container["searched"] = True
        container["discovered_count"] = len(evidence)
        self._sync_discovered_evidence()
        newly_discovered = [
            item for item in evidence if item.id not in before]
        site = self.world.storage_sites.get(container["storage_site_id"])
        access = site.accessibility if site is not None else "public"
        buried = sum(item.state == "buried" for item in evidence)
        if buried:
            summary = (
                f"你清理并记录了这处地点，找到{len(evidence)}件可辨认材料，"
                f"其中{buried}件原本埋藏在覆盖层下。")
        else:
            summary = f"你逐项检查了这处存储地点，找到{len(evidence)}件材料。"
        minutes = 60 if buried or container["placement_kind"] in {
            "excavation", "debris_search"} else 25
        return self._finish_action({
            "action": "search_container",
            "container": {
                "id": container["id"],
                "name": container["name"],
                "accessibility": access,
                "accessibility_name": container["role_name"],
                "condition": container["condition"],
            },
            "description_cn": (
                f"{ACCESS_NOTES.get(access, '你完成了现场查验。')} {summary}"),
            "newly_discovered_count": len(newly_discovered),
            "discovered_evidence": [
                self._map_evidence_payload(item) for item in evidence],
            "local_map": self.local_map,
            "journal": self.journal_payload(),
        }, minutes)

    def read(self, evidence_id: str) -> dict:
        candidate = self.world.evidence.get(evidence_id)
        quick_read = candidate is not None and is_public_inscription(candidate)
        if quick_read and evidence_id not in self.knowledge.discovered_evidence_ids:
            marker = next(
                (item for item in self.local_map["entities"]
                 if item["kind"] == "evidence" and item["id"] == evidence_id),
                None,
            )
            if (marker is None
                    or candidate.location_id != self._active_location_id()
                    or candidate.state == "destroyed"):
                raise PlayerActionError("这里找不到这处铭文。")
            distance = (
                abs(marker["x"] - self.local_time.player["x"])
                + abs(marker["y"] - self.local_time.player["y"])
            )
            if distance > 1:
                raise PlayerActionError("需要先走到铭文旁边。")
            self.knowledge.discover_evidence(candidate.id)
            self._sync_discovered_evidence()
        evidence = self._local_evidence(evidence_id)
        if not quick_read:
            self._require_examined(evidence.id)
        if has_text_carrier(evidence):
            evidence = materialize_text_carrier(self.world, evidence.id)
        result = read_document(evidence, self.known_languages)
        reading = DocumentReading.from_result(
            evidence.id, self._active_location_id(), result)
        statements = ()
        record = self.world.records.get(evidence.source_record_id)
        if result.get("status") == "readable" and record is not None:
            statements = build_reading_statements(
                EvidencePublicView.from_evidence(evidence),
                reading,
                RecordPublicView.from_record_and_evidence(record, evidence),
            )
        learned = self.knowledge.record_reading(reading, statements)
        return self._finish_action({
            "action": "read",
            "evidence": self._evidence_payload(evidence),
            "reading": reading.to_dict(),
            "text_cn": result.get("text", "没有可读取的内容。"),
            "learned_claims": [item.to_dict() for item in learned],
            "local_map": self.local_map,
            "journal": self.journal_payload(),
        }, 5 if quick_read else 30)

    def consult(self, evidence_id: str, informant_id: str) -> dict:
        evidence = self._local_evidence(evidence_id)
        self._require_examined(evidence.id)
        informant = next(
            (item for item in self.world.get_available_informants(
                self.current_location_id)
             if item.id == informant_id),
            None,
        )
        if informant is None:
            raise PlayerActionError("这位知情人目前不在这里。")
        person = self.world.persons.get(informant.person_id)
        if person is None or not person.alive:
            raise PlayerActionError("这位知情人目前无法接受咨询。")

        consultant = ConsultantView.from_informant(informant, person)
        record = self.world.records.get(evidence.source_record_id)
        record_view = (
            RecordPublicView.from_record_and_evidence(record, evidence)
            if record is not None else None)
        reading_view = None
        if has_text_carrier(evidence):
            evidence = materialize_text_carrier(self.world, evidence.id)
            reading_view = ReadingPublicView.from_result(
                read_document(evidence, set(consultant.known_languages)))
        result = self._consultation_engine.consult(
            EvidencePublicView.from_evidence(evidence),
            consultant,
            reading=reading_view,
            record=record_view,
            held_knowledge=self._held_knowledge(informant),
        )
        learned = self.knowledge.learn_from_consultation(result)
        return self._finish_action({
            "action": "consult",
            "evidence": self._evidence_payload(evidence),
            "consultant": self._informant_payload(informant),
            "consultation": result.to_dict(),
            "learned_claims": [item.to_dict() for item in learned],
            "journal": self.journal_payload(),
        }, 20)

    def compare(self, first_id: str, second_id: str) -> dict:
        if first_id == second_id:
            raise PlayerActionError("请选择两件不同的证物。")
        first = self._local_evidence(first_id)
        second = self._local_evidence(second_id)
        self._require_examined(first.id)
        self._require_examined(second.id)
        first_observations = tuple(
            item for item in self.knowledge.observations.values()
            if item.evidence_id == first.id)
        second_observations = tuple(
            item for item in self.knowledge.observations.values()
            if item.evidence_id == second.id)
        result = self._comparison_engine.compare(
            EvidencePublicView.from_evidence(first),
            EvidencePublicView.from_evidence(second),
            first_observations,
            second_observations,
            self._source_groups_for_evidence(first.id),
            self._source_groups_for_evidence(second.id),
        )
        self.knowledge.record_comparison(result)
        return self._finish_action({
            "action": "compare",
            "comparison": result.to_dict(),
            "evidence": [
                self._evidence_payload(first),
                self._evidence_payload(second),
            ],
            "journal": self.journal_payload(),
        }, 10)

    def talk(self, resident_id: str) -> dict:
        resident = next(
            (item for item in self.local_map["entities"]
             if item["kind"] == "resident" and item["id"] == resident_id),
            None,
        )
        if resident is None:
            raise PlayerActionError("这位居民目前不在这里。")
        return self._finish_action({
            "action": "talk",
            "resident": {
                "id": resident["id"],
                "name": resident["name"],
                "role": resident["role"],
                "role_name": resident["role_name"],
                "zone": resident["zone"],
                "description_cn": resident["description_cn"],
            },
            "dialogue_cn": resident["dialogue_cn"],
        }, 5)

    def inspect_wilderness(self, entity_id: str) -> dict:
        entity = next(
            (item for item in self.local_map["entities"]
             if item["id"] == entity_id
             and item["kind"] in {
                 "landmark", "camp", "caravan", "traveler", "trace",
                 "wildlife"}),
            None,
        )
        if entity is None:
            raise PlayerActionError("这里没有这个荒野地点或旅行队伍。")
        position = (entity["x"], entity["y"])
        runtime_npc = self.local_time._npcs.get(entity_id)
        if runtime_npc is not None:
            position = (runtime_npc["x"], runtime_npc["y"])
        if (abs(position[0] - self.local_time.player["x"])
                + abs(position[1] - self.local_time.player["y"]) > 1):
            raise PlayerActionError("需要走近后才能查看或交谈。")
        return self._finish_action({
            "action": "inspect_wilderness",
            "subject": {
                "id": entity["id"],
                "name": entity["name"],
                "kind": entity["kind"],
                "subtype": entity["subtype"],
                "zone": entity["zone"],
                "cargo": list(entity.get("cargo", [])),
                "destination_name": entity.get("destination_name", ""),
                "religion_name": entity.get("religion_name", ""),
                "guard_count": int(entity.get("guard_count", 0)),
            },
            "description_cn": entity.get("description_cn", ""),
            "dialogue_cn": entity.get("dialogue_cn", ""),
        }, 3)

    def move(self, dx: int, dy: int) -> dict:
        try:
            result = self.local_time.move_player(dx, dy)
        except ValueError as exc:
            raise PlayerActionError(str(exc)) from exc
        if result.get("exit_map"):
            return self._move_to_adjacent_cell(result["exit_map"])
        if result.get("moved"):
            if self._advance_travel_time(1):
                result["local_map"] = self.local_map
                result["runtime"] = self.local_time.snapshot()
        return {"action": "move", **result}

    def wait(self, minutes: int = 10) -> dict:
        if minutes not in {5, 10, 15, 30, 60}:
            raise PlayerActionError("只能等待 5、10、15、30 或 60 分钟。")
        runtime = self.local_time.advance(minutes)
        changed = self._advance_travel_time(minutes)
        return {
            "action": "wait",
            "minutes": minutes,
            "runtime": self.local_time.snapshot() if changed else runtime,
            **({"local_map": self.local_map} if changed else {}),
        }

    def travel(self, destination_id: str) -> dict:
        destination = self.world.settlements.get(destination_id)
        if destination is None or not destination.alive:
            raise PlayerActionError("世界地图上没有这个可快速旅行的城镇。")
        if destination_id == self.current_location_id:
            raise PlayerActionError("你已经在这个地点。")
        self._remember_current_exploration()
        origin = self._current_settlement()
        origin_cell = self.current_cell
        distance = math.hypot(
            destination.grid_x - self.current_cell[0],
            destination.grid_y - self.current_cell[1],
        )
        travel_minutes = max(60, int(math.ceil(distance * 45 / 5) * 5))
        absolute_minutes = (
            (self.local_time.day - 1) * 24 * 60
            + self.local_time.minute_of_day
            + travel_minutes
        )
        day, minute_of_day = divmod(absolute_minutes, 24 * 60)
        self.world.advance_travel_groups(travel_minutes)
        self.current_location_id = destination_id
        self.current_cell = (int(destination.grid_x), int(destination.grid_y))
        self.local_map = self._map_repository.get(*self.current_cell)
        decorate_travel_groups(self.local_map, self.world)
        self._decorate_local_map_evidence()
        self.local_time = LocalTimeSimulation(
            self.local_map,
            day=day + 1,
            minute_of_day=minute_of_day,
            settle_npcs=True,
            world_seed=self.world.seed,
            location_id=cell_key(*self.current_cell),
            biome=str(destination.biome),
            full_map_vision=self.full_map_vision,
        )
        self._restore_current_exploration()
        self._sync_discovered_evidence()
        return {
            "action": "travel",
            "origin": {
                "id": origin.id if origin is not None else cell_key(*origin_cell),
                "name": origin.name if origin is not None else "荒野",
            },
            "destination": {
                "id": destination.id,
                "name": destination.name,
                "site_type": "settlement" if destination.alive else "ruin",
            },
            "elapsed_minutes": travel_minutes,
            "location": self._location_payload(),
            "world_map": self._world_map_payload(),
        }

    def journal_payload(self) -> dict:
        evidence_names = {
            item.id: item.physical_features.get(
                "display_name", item.subtype.replace("_", " "))
            for item in self.world.evidence.values()
            if item.id in self.knowledge.discovered_evidence_ids
        }
        return {
            "counts": {
                "discovered": len(self.knowledge.discovered_evidence_ids),
                "examined": len(self.knowledge.examined_evidence_ids),
                "read": len(self.knowledge.read_evidence_ids),
                "observations": len(self.knowledge.observations),
                "statements": len(self.knowledge.source_statements),
                "claims": len(self.knowledge.known_claims),
                "conflicts": len(self.knowledge.conflicts),
                "comparisons": len(self.knowledge.comparisons),
                "source_groups": len(self.knowledge.source_groups),
            },
            "evidence_names": evidence_names,
            "observations": [
                item.to_dict() for item in sorted(
                    self.knowledge.observations.values(),
                    key=lambda value: (value.evidence_id, value.id))
            ],
            "readings": [
                item.to_dict() for item in sorted(
                    self.knowledge.document_readings.values(),
                    key=lambda value: (value.evidence_id, value.id))
            ],
            "statements": [
                item.to_dict() for item in sorted(
                    self.knowledge.source_statements.values(),
                    key=lambda value: value.id)
            ],
            "claims": [
                item.to_dict() for item in self.knowledge.sorted_claims()
            ],
            "conflicts": [
                item.to_dict() for item in sorted(
                    self.knowledge.conflicts.values(),
                    key=lambda value: value.id)
            ],
            "comparisons": [
                item.to_dict() for item in sorted(
                    self.knowledge.comparisons.values(),
                    key=lambda value: value.id)
            ],
        }

    def _finish_action(self, payload: dict, minutes: int) -> dict:
        payload["runtime"] = self.local_time.advance(minutes)
        if self._advance_travel_time(minutes):
            payload["local_map"] = self.local_map
            payload["runtime"] = self.local_time.snapshot()
        payload["elapsed_minutes"] = minutes
        return payload

    def _advance_travel_time(self, minutes: int) -> bool:
        before = {
            item.id for item in self.world.get_travel_groups_at(
                *self.current_cell)}
        before_camps = self.world.camp_signature(*self.current_cell)
        self.world.advance_travel_groups(minutes)
        after = {
            item.id for item in self.world.get_travel_groups_at(
                *self.current_cell)}
        after_camps = self.world.camp_signature(*self.current_cell)
        if before == after and before_camps == after_camps:
            return False
        previous = self.local_time
        decorate_travel_groups(self.local_map, self.world)
        self.local_map = copy.deepcopy(self.local_map)
        self._map_repository.maps[cell_key(*self.current_cell)] = self.local_map
        biome = str(self.world.geography.biomes[
            self.current_cell[1], self.current_cell[0]])
        refreshed = LocalTimeSimulation(
            self.local_map,
            day=previous.day,
            minute_of_day=previous.minute_of_day,
            settle_npcs=True,
            world_seed=self.world.seed,
            location_id=cell_key(*self.current_cell),
            biome=biome,
            player_position=(previous.player["x"], previous.player["y"]),
            full_map_vision=self.full_map_vision,
        )
        refreshed.turn = previous.turn
        refreshed._explored_cells = set(previous._explored_cells)
        self.local_time = refreshed
        return True

    def _location_payload(self) -> dict:
        settlement = self._current_settlement()
        return {
            "settlement": {
                "id": settlement.id,
                "name": settlement.name,
                "size": settlement.size,
                "biome": settlement.biome,
                "population": settlement.population,
                "alive": settlement.alive,
            } if settlement is not None else None,
            "cell": {"x": self.current_cell[0], "y": self.current_cell[1]},
            "local_map": self.local_map,
            "runtime": self.local_time.snapshot(),
            "informants": self._informants_payload(),
        }

    def _world_map_payload(self) -> dict:
        geography = self.world.geography
        terrain = [
            [PLAYER_BIOME_CODES[str(geography.biomes[y, x])]
             for x in range(geography.width)]
            for y in range(geography.height)
        ]
        territory = build_territory_payload(
            self.world, terrain, PLAYER_BIOME_CODES)
        polity_codes = {
            polity["id"]: polity["code"]
            for polity in territory["polities"]
        }
        locations = [
            {
                "id": settlement.id,
                "name": settlement.name,
                "x": int(settlement.grid_x),
                "y": int(settlement.grid_y),
                "site_type": "settlement" if settlement.alive else "ruin",
                "size": settlement.size,
                "biome": str(settlement.biome),
                "polity_code": polity_codes.get(
                    settlement.controller_polity_id),
            }
            for settlement in sorted(
                self.world.settlements.values(), key=lambda item: item.id)
        ]
        return {
            "width": geography.width,
            "height": geography.height,
            "terrain": terrain,
            "biome_codes": dict(PLAYER_BIOME_CODES),
            "territory": {
                "unclaimed_code": territory["unclaimed_code"],
                "owners": territory["owners"],
                "polities": [
                    {"code": polity["code"], "name": polity["name"]}
                    for polity in territory["polities"]
                ],
            },
            "locations": locations,
            "geographic_features": [
                {
                    "id": feature.id,
                    "feature_type": feature.feature_type,
                    "feature_type_name": feature.to_dict()[
                        "feature_type_name"],
                    "name": feature.name,
                    "x": feature.anchor[0],
                    "y": feature.anchor[1],
                    "size": feature.size,
                    "importance": feature.importance,
                    "min_zoom": feature.min_zoom,
                    "bounds": list(feature.bounds),
                    "meaning_tags": list(feature.meaning_tags),
                }
                for feature in geography.features
            ],
            "current_location_id": self.current_location_id,
            "current_cell": {
                "x": self.current_cell[0], "y": self.current_cell[1]},
            "routes": [
                {
                    "id": route.id,
                    "status": route.status,
                    "path": [{"x": x, "y": y} for x, y in route.path],
                }
                for route in sorted(
                    self.world.trade_routes.values(), key=lambda item: item.id)
                if route.status == "active"
            ],
        }

    def _current_settlement(self):
        if self.current_location_id is None:
            return None
        return self.world.settlements.get(self.current_location_id)

    def _active_location_id(self) -> str:
        return self.current_location_id or cell_key(*self.current_cell)

    def _remember_current_exploration(self) -> None:
        self._explored_by_cell[cell_key(*self.current_cell)] = set(
            self.local_time._explored_cells)

    def _restore_current_exploration(self) -> None:
        self.local_time._explored_cells.update(
            self._explored_by_cell.get(cell_key(*self.current_cell), set()))

    def _move_to_adjacent_cell(self, exit_data: dict) -> dict:
        direction = str(exit_data["direction"])
        dx, dy = {
            "north": (0, -1), "south": (0, 1),
            "west": (-1, 0), "east": (1, 0),
        }[direction]
        target = (self.current_cell[0] + dx, self.current_cell[1] + dy)
        geography = self.world.geography
        if not (0 <= target[0] < geography.width
                and 0 <= target[1] < geography.height):
            raise PlayerActionError("这里已经是世界的边界。")
        biome = str(geography.biomes[target[1], target[0]])
        if biome in {"ocean", "lake"}:
            raise PlayerActionError("没有船只，无法进入这片水域。")

        self._remember_current_exploration()
        next_map = self._map_repository.get(*target)
        self.world.advance_travel_groups(1)
        decorate_travel_groups(next_map, self.world)
        fraction = float(exit_data["offset"]) / max(
            1, int(exit_data["span"]) - 1)
        if direction == "north":
            desired = (round(fraction * (next_map["width"] - 1)),
                       next_map["height"] - 1)
        elif direction == "south":
            desired = (round(fraction * (next_map["width"] - 1)), 0)
        elif direction == "west":
            desired = (next_map["width"] - 1,
                       round(fraction * (next_map["height"] - 1)))
        else:
            desired = (0, round(fraction * (next_map["height"] - 1)))
        spawn = self._nearest_walkable(next_map, desired)
        settlement = self.world.get_settlement_at(*target)
        source_day = self.local_time.day
        source_minute = self.local_time.minute_of_day
        self.current_cell = target
        self.current_location_id = settlement.id if settlement is not None else None
        self.local_map = next_map
        self._decorate_local_map_evidence()
        self.local_time = LocalTimeSimulation(
            self.local_map,
            day=source_day,
            minute_of_day=source_minute,
            settle_npcs=True,
            world_seed=self.world.seed,
            location_id=cell_key(*target),
            biome=biome,
            player_position=spawn,
            full_map_vision=self.full_map_vision,
        )
        self._restore_current_exploration()
        runtime = self.local_time.advance(1)
        self._sync_discovered_evidence()
        return {
            "action": "move",
            "moved": True,
            "changed_map": True,
            "elapsed_minutes": 1,
            "runtime": runtime,
            "location": self._location_payload(),
            "world_map": self._world_map_payload(),
        }

    @staticmethod
    def _nearest_walkable(local_map: dict,
                          desired: tuple[int, int]) -> tuple[int, int]:
        width, height = local_map["width"], local_map["height"]
        blocking = set(local_map["blocking_tiles"])
        occupied = {
            (item["x"], item["y"]) for item in local_map["entities"]
            if item.get("blocks_movement", True)
        }
        for radius in range(max(width, height)):
            candidates = []
            for y in range(max(0, desired[1] - radius),
                           min(height, desired[1] + radius + 1)):
                for x in range(max(0, desired[0] - radius),
                               min(width, desired[0] + radius + 1)):
                    if abs(x - desired[0]) + abs(y - desired[1]) != radius:
                        continue
                    if ((x, y) not in occupied
                            and local_map["tiles"][y * width + x] not in blocking):
                        candidates.append((x, y))
            if candidates:
                return sorted(candidates, key=lambda item: (item[1], item[0]))[0]
        raise PlayerActionError("相邻地图没有可进入的位置。")

    def _starting_settlement_id(self) -> str:
        candidates = [
            settlement for settlement in self.world.settlements.values()
            if settlement.alive]
        if not candidates:
            candidates = list(self.world.settlements.values())
        if not candidates:
            raise PlayerActionError("世界中没有可进入的聚落。")
        candidates.sort(key=lambda settlement: (
            -len(self.world.get_all_visible_evidence(settlement.id)),
            -len(self.world.get_available_informants(settlement.id)),
            settlement.id,
        ))
        return candidates[0].id

    def _local_evidence(self, evidence_id: str):
        evidence = self.world.evidence.get(evidence_id)
        if (evidence is None
                or evidence.id not in self.knowledge.discovered_evidence_ids
                or evidence.location_id != self._active_location_id()
                or evidence.state == "destroyed"
                or evidence.evidence_type == "oral"):
            raise PlayerActionError("这里找不到这件证物。")
        return evidence

    def _require_examined(self, evidence_id: str) -> None:
        if evidence_id not in self.knowledge.examined_evidence_ids:
            raise PlayerActionError("需要先检查这件证物。")

    def _evidence_payload(self, evidence) -> dict:
        view = EvidencePublicView.from_evidence(evidence)
        payload = view.to_dict()
        # Raw feature codes and analysis routing are investigation internals.
        payload.pop("tags", None)
        payload.pop("analysis_domains", None)
        payload.pop("location_id", None)
        payload["can_read"] = has_text_carrier(evidence)
        payload["quick_read"] = is_public_inscription(evidence)
        payload["description_cn"] = self._glance_description(evidence)
        payload["examined"] = evidence.id in self.knowledge.examined_evidence_ids
        payload["read"] = evidence.id in self.knowledge.read_evidence_ids
        payload["source_group_ids"] = list(
            self._source_groups_for_evidence(evidence.id))
        return payload

    def _sync_discovered_evidence(self) -> None:
        self.local_map["discovered_evidence"] = [
            self._map_evidence_payload(item)
            for item in sorted(
                self.world.evidence.values(),
                key=lambda value: (
                    value.container_id or "", value.storage_position, value.id),
            )
            if item.id in self.knowledge.discovered_evidence_ids
            and item.location_id == self._active_location_id()
            and item.state != "destroyed"
            and item.evidence_type != "oral"
        ]

    def _map_evidence_payload(self, evidence) -> dict:
        target = next(
            (item for item in build_evidence_targets(
                self.world.evidence.values(), self.world.storage_sites,
                self._active_location_id())
             if evidence.id in item["evidence_ids"]),
            None,
        )
        if target is None:
            raise PlayerActionError("证物的物理存放方式不存在。")
        map_target = next(
            (item for item in self.local_map["entities"]
             if item["id"] == target["id"]),
            None,
        )
        if map_target is None:
            raise PlayerActionError("证物的物理存储地点不存在。")
        site = self.world.storage_sites.get(evidence.container_id)
        return {
            "id": evidence.id,
            "kind": "evidence",
            "x": map_target["x"],
            "y": map_target["y"],
            "name": evidence.physical_features.get(
                "display_name", evidence.subtype.replace("_", " ")),
            "subtype": evidence.evidence_type,
            "role": "",
            "role_name": "",
            "state": evidence.state,
            "material": evidence.material,
            "zone": site.name if site is not None else map_target["name"],
            "description_cn": self._glance_description(evidence),
            "dialogue_cn": "",
            "container_id": target["id"],
            "storage_site_id": evidence.container_id or "",
            "storage_position": (
                map_target["name"] if target["kind"] == "container"
                else evidence.storage_position or "原位置"),
            "placement_kind": target["placement_kind"],
            "blocks_movement": False,
            "can_read": has_text_carrier(evidence),
            "quick_read": is_public_inscription(evidence),
        }

    def _glance_description(self, evidence) -> str:
        preview = preview_public_inscription(
            evidence, self.known_languages)
        return describe_at_glance(
            build_evidence_context(evidence), preview)

    def _decorate_local_map_evidence(self) -> None:
        """Attach only plain-sight information to direct map evidence."""
        for entity in self.local_map["entities"]:
            if entity["kind"] != "evidence":
                continue
            evidence = self.world.evidence.get(entity["id"])
            if evidence is None:
                continue
            entity["description_cn"] = self._glance_description(evidence)
            entity["can_read"] = has_text_carrier(evidence)
            entity["quick_read"] = is_public_inscription(evidence)

    def _informants_payload(self) -> list[dict]:
        return [
            self._informant_payload(item)
            for item in self.world.get_available_informants(
                self.current_location_id)
        ]

    def _informant_payload(self, informant) -> dict:
        person = self.world.persons[informant.person_id]
        home = self.world.settlements.get(person.settlement_id)
        base_role_name = ROLE_NAMES.get(informant.role, informant.role)
        travel_role_name = public_travel_role(person)
        public_status = public_mobility_status(person)
        claimed_origin_name = ""
        origin_knowledge_status = "unknown"
        if public_status == "resident":
            presence_label = f"{base_role_name} · 本地居民"
        elif public_status == "survivor":
            presence_label = f"{travel_role_name or '幸存者'} · 留在此处废墟"
        elif person.travel_role == "captive" or (
                person.travel_role in HIDDEN_TRAVEL_ROLES):
            presence_label = travel_role_name or "身份未明的外地人"
        else:
            claimed_origin_name = home.name if home is not None else ""
            if claimed_origin_name:
                origin_knowledge_status = "self_reported"
                presence_label = (
                    f"{travel_role_name or base_role_name} · 自称来自"
                    f"{claimed_origin_name}")
            else:
                presence_label = travel_role_name or "外地访客"
        return {
            "id": informant.id,
            "name": person.name,
            "role": informant.role,
            "role_name": travel_role_name or base_role_name,
            "base_role_name": base_role_name,
            "public_status": public_status,
            "public_role_name": travel_role_name or base_role_name,
            "claimed_origin_name": claimed_origin_name,
            "origin_knowledge_status": origin_knowledge_status,
            "presence_label": presence_label,
        }

    def _held_knowledge(self, informant) -> tuple[HeldKnowledgeView, ...]:
        views = []
        for entry in sorted(
                self.world.get_informant_knowledge(informant.id),
                key=lambda item: item.id):
            evidence = self.world.evidence.get(entry.source_evidence_id)
            record = self.world.records.get(entry.source_record_id)
            if evidence is None or record is None:
                continue
            view = HeldKnowledgeView.from_entry_record_and_evidence(
                entry, record, evidence)
            if view.record.claims:
                views.append(view)
        return tuple(views)

    def _source_groups_for_evidence(self, evidence_id: str) -> tuple[str, ...]:
        return tuple(sorted(
            group.id for group in self.knowledge.source_groups.values()
            if evidence_id in group.evidence_ids))
