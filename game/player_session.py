"""Truth-isolated state and actions for the browser play prototype."""

from __future__ import annotations

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
from game.local_map import LocalMapBuilder
from game.observation import build_evidence_observations
from narrative.context_builder import build_evidence_context
from narrative.document_reader import read_document
from narrative.evidence_describer import describe_evidence


ROLE_NAMES = {
    "scholar": "学者",
    "scribe": "书记",
    "elder": "地方长者",
    "merchant": "商人",
    "artisan": "工匠",
}


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
        self.current_location_id = settlement_id or self._starting_settlement_id()
        settlement = self.world.settlements[self.current_location_id]
        self.local_map = LocalMapBuilder().build(self.world, settlement)

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
            "informants": self._informants_payload(),
            "journal": self.journal_payload(),
        }

    def examine(self, evidence_id: str) -> dict:
        evidence = self._local_evidence(evidence_id)
        view = EvidencePublicView.from_evidence(evidence)
        observations = build_evidence_observations(view)
        added = self.knowledge.record_observations(evidence.id, observations)
        return {
            "action": "examine",
            "evidence": self._evidence_payload(evidence),
            "description_cn": describe_evidence(build_evidence_context(evidence)),
            "observations": [item.to_dict() for item in observations],
            "new_observation_count": added,
            "journal": self.journal_payload(),
        }

    def read(self, evidence_id: str) -> dict:
        evidence = self._local_evidence(evidence_id)
        self._require_examined(evidence.id)
        result = read_document(evidence, self.known_languages)
        reading = DocumentReading.from_result(
            evidence.id, self.current_location_id, result)
        statements = ()
        record = self.world.records.get(evidence.source_record_id)
        if result.get("status") == "readable" and record is not None:
            statements = build_reading_statements(
                EvidencePublicView.from_evidence(evidence),
                reading,
                RecordPublicView.from_record_and_evidence(record, evidence),
            )
        learned = self.knowledge.record_reading(reading, statements)
        return {
            "action": "read",
            "evidence": self._evidence_payload(evidence),
            "reading": reading.to_dict(),
            "text_cn": result.get("text", "没有可读取的内容。"),
            "learned_claims": [item.to_dict() for item in learned],
            "journal": self.journal_payload(),
        }

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
        if evidence.evidence_type == "document":
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
        return {
            "action": "consult",
            "evidence": self._evidence_payload(evidence),
            "consultant": self._informant_payload(informant),
            "consultation": result.to_dict(),
            "learned_claims": [item.to_dict() for item in learned],
            "journal": self.journal_payload(),
        }

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
        return {
            "action": "compare",
            "comparison": result.to_dict(),
            "evidence": [
                self._evidence_payload(first),
                self._evidence_payload(second),
            ],
            "journal": self.journal_payload(),
        }

    def talk(self, resident_id: str) -> dict:
        resident = next(
            (item for item in self.local_map["entities"]
             if item["kind"] == "resident" and item["id"] == resident_id),
            None,
        )
        if resident is None:
            raise PlayerActionError("这位居民目前不在这里。")
        return {
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
        visible_ids = {
            item.id for item in self.world.get_all_visible_evidence(
                self.current_location_id)}
        if evidence is None or evidence.id not in visible_ids:
            raise PlayerActionError("这里找不到这件证物。")
        return evidence

    def _require_examined(self, evidence_id: str) -> None:
        if evidence_id not in self.knowledge.examined_evidence_ids:
            raise PlayerActionError("需要先检查这件证物。")

    def _evidence_payload(self, evidence) -> dict:
        view = EvidencePublicView.from_evidence(evidence)
        payload = view.to_dict()
        payload["can_read"] = evidence.evidence_type == "document"
        payload["examined"] = evidence.id in self.knowledge.examined_evidence_ids
        payload["read"] = evidence.id in self.knowledge.read_evidence_ids
        payload["source_group_ids"] = list(
            self._source_groups_for_evidence(evidence.id))
        return payload

    def _informants_payload(self) -> list[dict]:
        return [
            self._informant_payload(item)
            for item in self.world.get_available_informants(
                self.current_location_id)
        ]

    def _informant_payload(self, informant) -> dict:
        person = self.world.persons[informant.person_id]
        return {
            "id": informant.id,
            "name": person.name,
            "role": informant.role,
            "role_name": ROLE_NAMES.get(informant.role, informant.role),
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
