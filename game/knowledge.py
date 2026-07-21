"""Player-owned claims reconstructed from evidence, never from event truth."""

from __future__ import annotations

from dataclasses import dataclass, field

from game.investigation import (
    ClaimConflict,
    ComparisonResult,
    ConsultationResult,
    DocumentReading,
    Observation,
    SourceGroup,
    SourceStatement,
    source_group_id,
    stable_investigation_id,
)


STATUS_THRESHOLDS = (
    (0.82, "高度可信"),
    (0.62, "可信"),
    (0.42, "可能"),
    (0.0, "传闻"),
)

CONFIDENCE_COMPONENT_KEYS = (
    "carrier_quality",
    "directness",
    "expertise_match",
    "comprehension",
    "temporal_proximity",
    "source_independence",
    "corroboration",
    "contradiction",
    "bias_penalty",
    "transmission_penalty",
)

EXCLUSIVE_PREDICATES = {"war_result", "rebellion_result"}

DIRECTNESS_WEIGHTS = {
    "document_transcription": 0.10,
    "transcription": 0.10,
    "partial_reading": 0.06,
    "scholarly_recollection": 0.05,
    "professional_recollection": 0.04,
    "oral_claim": 0.04,
}

BIAS_PENALTIES = {
    "scholarly": 0.01,
    "eyewitness": 0.02,
    "merchant": 0.03,
    "author": 0.03,
    "official": 0.04,
    "folk": 0.04,
    "opposition": 0.05,
}


@dataclass
class KnownClaim:
    subject: str
    predicate: str
    object: str
    statement_cn: str
    time_range: tuple[int, int]
    supporting_evidence_ids: list[str] = field(default_factory=list)
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    source_record_roots: list[str] = field(default_factory=list)
    source_groups: list[str] = field(default_factory=list)
    supporting_statement_ids: list[str] = field(default_factory=list)
    contradicting_statement_ids: list[str] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    confidence_components: dict[str, float] = field(default_factory=dict)
    base_confidence: float = 0.0
    confidence: float = 0.0
    status: str = "传闻"

    def semantic_key(self) -> str:
        return f"{self.subject}|{self.predicate}|{self.object}"

    def topic_key(self) -> str:
        return f"{self.subject}|{self.predicate}"

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "statement_cn": self.statement_cn,
            "time_range": list(self.time_range),
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids": list(self.contradicting_evidence_ids),
            "source_record_roots": list(self.source_record_roots),
            "source_groups": list(self.source_groups),
            "supporting_statement_ids": list(
                self.supporting_statement_ids),
            "contradicting_statement_ids": list(
                self.contradicting_statement_ids),
            "conflict_ids": list(self.conflict_ids),
            "confidence_components": dict(self.confidence_components),
            "base_confidence": self.base_confidence,
            "confidence": self.confidence,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnownClaim":
        time_range = data.get("time_range", [0, 0])
        roots = list(data.get("source_record_roots", []))
        return cls(
            subject=data.get("subject", "未知对象"),
            predicate=data.get("predicate", "unknown"),
            object=data.get("object", "unknown"),
            statement_cn=data.get("statement_cn", "主张内容不明。"),
            time_range=(int(time_range[0]), int(time_range[1])),
            supporting_evidence_ids=list(
                data.get("supporting_evidence_ids", [])),
            contradicting_evidence_ids=list(
                data.get("contradicting_evidence_ids", [])),
            source_record_roots=roots,
            source_groups=list(data.get("source_groups", (
                source_group_id(root_id) for root_id in roots))),
            supporting_statement_ids=list(data.get(
                "supporting_statement_ids", [])),
            contradicting_statement_ids=list(data.get(
                "contradicting_statement_ids", [])),
            conflict_ids=list(data.get("conflict_ids", [])),
            confidence_components={
                key: float(value) for key, value
                in data.get("confidence_components", {}).items()
            },
            base_confidence=float(data.get(
                "base_confidence", data.get("confidence", 0.0))),
            confidence=float(data.get("confidence", 0.0)),
            status=data.get("status", "传闻"),
        )


@dataclass
class PlayerKnowledge:
    discovered_evidence_ids: set[str] = field(default_factory=set)
    examined_evidence_ids: set[str] = field(default_factory=set)
    read_evidence_ids: set[str] = field(default_factory=set)
    observations: dict[str, Observation] = field(default_factory=dict)
    document_readings: dict[str, DocumentReading] = field(
        default_factory=dict)
    known_claims: dict[str, KnownClaim] = field(default_factory=dict)
    source_statements: dict[str, SourceStatement] = field(default_factory=dict)
    consultations: dict[str, ConsultationResult] = field(default_factory=dict)
    source_groups: dict[str, SourceGroup] = field(default_factory=dict)
    conflicts: dict[str, ClaimConflict] = field(default_factory=dict)
    comparisons: dict[str, ComparisonResult] = field(default_factory=dict)
    schema_version: int = 3

    def discover_evidence(self, evidence_id: str) -> None:
        self.discovered_evidence_ids.add(evidence_id)

    def record_observations(
            self, evidence_id: str,
            observations: list[Observation] | tuple[Observation, ...]) -> int:
        """Persist objective observations and mark the carrier examined."""
        self.discovered_evidence_ids.add(evidence_id)
        self.examined_evidence_ids.add(evidence_id)
        added = 0
        for observation in observations:
            if observation.id in self.observations:
                continue
            self.observations[observation.id] = observation
            added += 1
        return added

    def record_reading(
            self, reading: DocumentReading,
            statements: tuple[SourceStatement, ...] = ()) -> list[KnownClaim]:
        """Persist visible text and any claims actually recovered from it."""
        self.document_readings.setdefault(reading.id, reading)
        if reading.status == "readable":
            self.read_evidence_ids.add(reading.evidence_id)
        return self.learn_from_statements(statements)

    def record_comparison(self, result: ComparisonResult) -> bool:
        """Persist one deterministic comparison without duplicating it."""
        if result.id in self.comparisons:
            return False
        self.comparisons[result.id] = result
        return True

    def learn_from_record(self, record, evidence, comprehension: float,
                          expertise_bonus: float = 0.0) -> list[KnownClaim]:
        """Learn only claims carried by the supplied record and evidence."""
        if comprehension + expertise_bonus < 0.20:
            return []
        retained = set(evidence.retained_claim_ids)
        available = [
            claim for claim in record.claimed_facts
            if claim.id in retained
        ]
        if not available:
            return []
        count = max(1, round(len(available) * min(
            1.0, comprehension + expertise_bonus)))
        learned = []
        for claim in available[:count]:
            learned.append(self._add_support(
                claim, record, evidence, comprehension, expertise_bonus))
        self._mark_contradictions()
        return learned

    def learn_from_consultation(
            self, result: ConsultationResult) -> list[KnownClaim]:
        """Store one sourced consultation without rewarding repetition."""
        if result.id in self.consultations:
            return []
        self.consultations[result.id] = result
        return self.learn_from_statements(result.statements)

    def learn_from_statements(
            self, statements: tuple[SourceStatement, ...]
            | list[SourceStatement]) -> list[KnownClaim]:
        """Store sourced statements and derive claims without duplication."""
        learned = []
        for statement in statements:
            if statement.id in self.source_statements:
                continue
            self.source_statements[statement.id] = statement
            self._register_source_group(statement)
            if statement.claim is None:
                continue
            if statement.comprehension + statement.expertise_bonus < 0.20:
                continue
            learned.append(self._add_statement_support(statement))
        self._mark_contradictions()
        return learned

    def _add_statement_support(
            self, statement: SourceStatement) -> KnownClaim:
        claim = statement.claim
        key = claim.semantic_key()
        known = self.known_claims.get(key)
        if known is None:
            known = KnownClaim(
                subject=claim.subject,
                predicate=claim.predicate,
                object=claim.object,
                statement_cn=claim.statement_cn,
                time_range=claim.time_range,
            )
            self.known_claims[key] = known
        if statement.id not in known.supporting_statement_ids:
            known.supporting_statement_ids.append(statement.id)
        if (statement.source_evidence_id
                and statement.source_evidence_id
                not in known.supporting_evidence_ids):
            known.supporting_evidence_ids.append(
                statement.source_evidence_id)
        if (statement.source_record_root_id
                and statement.source_record_root_id
                not in known.source_record_roots):
            known.source_record_roots.append(
                statement.source_record_root_id)
        if (statement.source_group_id
                and statement.source_group_id not in known.source_groups):
            known.source_groups.append(statement.source_group_id)
        known.time_range = (
            min(known.time_range[0], claim.time_range[0]),
            max(known.time_range[1], claim.time_range[1]),
        )
        return known

    def _add_support(self, claim, record, evidence, comprehension: float,
                     expertise_bonus: float) -> KnownClaim:
        key = claim.semantic_key()
        known = self.known_claims.get(key)
        if known is None:
            known = KnownClaim(
                subject=claim.subject,
                predicate=claim.predicate,
                object=claim.object,
                statement_cn=claim.statement_cn,
                time_range=claim.time_range,
            )
            self.known_claims[key] = known
        if evidence.id not in known.supporting_evidence_ids:
            known.supporting_evidence_ids.append(evidence.id)
        root_id = record.copy_parent_id or record.id
        if root_id not in known.source_record_roots:
            known.source_record_roots.append(root_id)
        group_id = source_group_id(root_id)
        if group_id not in known.source_groups:
            known.source_groups.append(group_id)
        self._ensure_source_group(
            group_id,
            ("oral_tradition"
             if record.record_type == "oral_tradition"
             else "record_lineage"),
            root_id,
            evidence.id,
        )
        known.time_range = (
            min(known.time_range[0], claim.time_range[0]),
            max(known.time_range[1], claim.time_range[1]),
        )
        self._recompute_confidence(
            known, record.perspective, evidence, comprehension,
            expertise_bonus)
        return known

    def _mark_contradictions(self) -> None:
        claims = self.sorted_claims()
        self.conflicts = {}
        for claim in claims:
            claim.contradicting_evidence_ids = []
            claim.contradicting_statement_ids = []
            claim.conflict_ids = []
        for index, first in enumerate(claims):
            for second in claims[index + 1:]:
                if (first.topic_key() != second.topic_key()
                        or first.object == second.object
                        or first.predicate not in EXCLUSIVE_PREDICATES):
                    continue
                overlap = self._overlapping_support(first, second)
                if overlap is None:
                    continue
                overlap_range, first_ids, second_ids = overlap
                conflict_id = stable_conflict_id(
                    first.semantic_key(), second.semantic_key(), overlap_range)
                conflict = ClaimConflict(
                    id=conflict_id,
                    first_claim_key=first.semantic_key(),
                    second_claim_key=second.semantic_key(),
                    relation_type="exclusive",
                    strength="strong",
                    overlap_range=overlap_range,
                    first_statement_ids=tuple(first_ids),
                    second_statement_ids=tuple(second_ids),
                    reason_cn=(
                        "两个互斥主张描述同一主题，且其年代范围发生重叠。"),
                )
                self.conflicts[conflict_id] = conflict
                first.conflict_ids.append(conflict_id)
                second.conflict_ids.append(conflict_id)
                first.contradicting_statement_ids.extend(
                    item for item in second_ids
                    if item not in first.contradicting_statement_ids)
                second.contradicting_statement_ids.extend(
                    item for item in first_ids
                    if item not in second.contradicting_statement_ids)
                for evidence_id in second.supporting_evidence_ids:
                    if evidence_id not in first.contradicting_evidence_ids:
                        first.contradicting_evidence_ids.append(evidence_id)
                for evidence_id in first.supporting_evidence_ids:
                    if evidence_id not in second.contradicting_evidence_ids:
                        second.contradicting_evidence_ids.append(evidence_id)
        for claim in claims:
            self._recompute_claim_confidence(claim)

    def _overlapping_support(
            self, first: KnownClaim, second: KnownClaim
            ) -> tuple[tuple[int, int], list[str], list[str]] | None:
        first_ranges = self._statement_ranges(first)
        second_ranges = self._statement_ranges(second)
        overlaps = []
        for first_id, first_range in first_ranges:
            for second_id, second_range in second_ranges:
                start = max(first_range[0], second_range[0])
                end = min(first_range[1], second_range[1])
                if start <= end:
                    overlaps.append((start, end, first_id, second_id))
        if not overlaps:
            return None
        first_ids = sorted({item[2] for item in overlaps if item[2]})
        second_ids = sorted({item[3] for item in overlaps if item[3]})
        return (
            (min(item[0] for item in overlaps),
             max(item[1] for item in overlaps)),
            first_ids,
            second_ids,
        )

    def _statement_ranges(
            self, claim: KnownClaim
            ) -> list[tuple[str | None, tuple[int, int]]]:
        ranges = []
        for statement_id in claim.supporting_statement_ids:
            statement = self.source_statements.get(statement_id)
            if statement is not None and statement.claim is not None:
                ranges.append((statement_id, statement.claim.time_range))
        return ranges or [(None, claim.time_range)]

    def _recompute_confidence(self, known: KnownClaim, perspective: str,
                              evidence, comprehension: float,
                              expertise_bonus: float) -> None:
        condition = (
            evidence.current_durability / evidence.max_durability
            if evidence.max_durability > 0 else 0.0)
        self._recompute_confidence_values(
            known, perspective, condition, comprehension, expertise_bonus)

    def _recompute_confidence_values(
            self, known: KnownClaim, perspective: str, condition: float,
            comprehension: float, expertise_bonus: float) -> None:
        independent_sources = len(
            known.source_groups or known.source_record_roots)
        known.confidence_components = self._empty_confidence_components()
        known.confidence_components.update({
            "carrier_quality": 0.12 * self._clamp(condition),
            "directness": 0.08,
            "expertise_match": 0.10 * self._clamp(
                expertise_bonus / 0.35),
            "comprehension": 0.10 * self._clamp(comprehension),
            "source_independence": 0.16 * min(independent_sources, 3),
            "bias_penalty": -BIAS_PENALTIES.get(perspective, 0.03),
        })
        self._apply_confidence(known)

    def _recompute_claim_confidence(self, known: KnownClaim) -> None:
        statements = [
            self.source_statements[statement_id]
            for statement_id in known.supporting_statement_ids
            if statement_id in self.source_statements
        ]
        if not statements:
            if known.confidence_components:
                known.confidence_components["contradiction"] = (
                    -0.12 if known.conflict_ids else 0.0)
                self._apply_confidence(known)
            else:
                known.confidence = max(
                    0.05,
                    known.base_confidence
                    - (0.12 if known.conflict_ids else 0.0),
                )
                known.status = self._status_for(known.confidence)
            return

        grouped: dict[str, list[SourceStatement]] = {}
        for statement in statements:
            group_key = statement.source_group_id or statement.id
            grouped.setdefault(group_key, []).append(statement)

        best_carrier = [
            max(item.carrier_condition for item in group)
            for group in grouped.values()]
        best_comprehension = [
            max(item.comprehension for item in group)
            for group in grouped.values()]
        best_expertise = [
            max(item.expertise_bonus for item in group)
            for group in grouped.values()]
        best_directness = [
            max(DIRECTNESS_WEIGHTS.get(item.statement_type, 0.03)
                for item in group)
            for group in grouped.values()]
        least_transmission = [
            min(item.transmission_depth for item in group)
            for group in grouped.values()]
        least_bias = [
            min(BIAS_PENALTIES.get(item.perspective, 0.03)
                for item in group)
            for group in grouped.values()]
        group_types = {
            item.source_group_type for item in statements
            if item.source_group_id}

        components = self._empty_confidence_components()
        components.update({
            "carrier_quality": 0.12 * self._average(best_carrier),
            "directness": self._average(best_directness),
            "expertise_match": 0.10 * self._clamp(
                self._average(best_expertise) / 0.35),
            "comprehension": 0.10 * self._average(best_comprehension),
            "source_independence": 0.16 * min(len(grouped), 3),
            "corroboration": (
                0.04 if len(grouped) >= 2 and len(group_types) >= 2
                else 0.0),
            "contradiction": -0.12 if known.conflict_ids else 0.0,
            "bias_penalty": -self._average(least_bias),
            "transmission_penalty": -min(
                0.15, 0.03 * self._average(least_transmission)),
        })
        known.confidence_components = {
            key: round(value, 6) for key, value in components.items()}
        self._apply_confidence(known)

    @staticmethod
    def _empty_confidence_components() -> dict[str, float]:
        return {key: 0.0 for key in CONFIDENCE_COMPONENT_KEYS}

    @staticmethod
    def _average(values: list[float] | list[int]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def _apply_confidence(self, known: KnownClaim) -> None:
        base_components = {
            key: value for key, value in known.confidence_components.items()
            if key != "contradiction"}
        known.base_confidence = min(
            0.95, max(0.05, 0.18 + sum(base_components.values())))
        known.confidence = min(
            0.95, max(
                0.05,
                known.base_confidence
                + known.confidence_components.get("contradiction", 0.0),
            ))
        known.base_confidence = round(known.base_confidence, 6)
        known.confidence = round(known.confidence, 6)
        known.status = self._status_for(known.confidence)

    @staticmethod
    def _status_for(confidence: float) -> str:
        for threshold, label in STATUS_THRESHOLDS:
            if confidence >= threshold:
                return label
        return "传闻"

    def sorted_claims(self) -> list[KnownClaim]:
        return sorted(
            self.known_claims.values(),
            key=lambda claim: (
                claim.time_range[0], claim.subject, claim.predicate,
                claim.object),
        )

    def search(self, query: str) -> list[KnownClaim]:
        normalized = query.casefold()
        return [
            claim for claim in self.sorted_claims()
            if normalized in claim.statement_cn.casefold()
            or normalized in claim.subject.casefold()
            or normalized in claim.object.casefold()
        ]

    def _register_source_group(self, statement: SourceStatement) -> None:
        if not statement.source_group_id or not statement.source_record_root_id:
            return
        group = self._ensure_source_group(
            statement.source_group_id,
            statement.source_group_type,
            statement.source_record_root_id,
            statement.source_evidence_id,
        )
        if statement.id not in group.statement_ids:
            group.statement_ids.append(statement.id)

    def _ensure_source_group(
            self, group_id: str, group_type: str, root_record_id: str,
            evidence_id: str | None = None) -> SourceGroup:
        group = self.source_groups.get(group_id)
        if group is None:
            group = SourceGroup(
                id=group_id,
                group_type=group_type,
                root_record_id=root_record_id,
            )
            self.source_groups[group_id] = group
        if evidence_id and evidence_id not in group.evidence_ids:
            group.evidence_ids.append(evidence_id)
        return group

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "discovered_evidence_ids": sorted(self.discovered_evidence_ids),
            "examined_evidence_ids": sorted(self.examined_evidence_ids),
            "read_evidence_ids": sorted(self.read_evidence_ids),
            "observations": {
                key: observation.to_dict()
                for key, observation in self.observations.items()
            },
            "document_readings": {
                key: reading.to_dict()
                for key, reading in self.document_readings.items()
            },
            "known_claims": {
                key: claim.to_dict()
                for key, claim in self.known_claims.items()
            },
            "source_statements": {
                key: statement.to_dict()
                for key, statement in self.source_statements.items()
            },
            "consultations": {
                key: consultation.to_dict()
                for key, consultation in self.consultations.items()
            },
            "source_groups": {
                key: group.to_dict()
                for key, group in self.source_groups.items()
            },
            "conflicts": {
                key: conflict.to_dict()
                for key, conflict in self.conflicts.items()
            },
            "comparisons": {
                key: comparison.to_dict()
                for key, comparison in self.comparisons.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerKnowledge":
        knowledge = cls(
            discovered_evidence_ids=set(
                data.get("discovered_evidence_ids", [])),
            examined_evidence_ids=set(
                data.get("examined_evidence_ids", [])),
            read_evidence_ids=set(data.get("read_evidence_ids", [])),
            observations={
                key: Observation.from_dict(value)
                for key, value in data.get("observations", {}).items()
            },
            document_readings={
                key: DocumentReading.from_dict(value)
                for key, value in data.get("document_readings", {}).items()
            },
            known_claims={
                key: KnownClaim.from_dict(value)
                for key, value in data.get("known_claims", {}).items()
            },
            source_statements={
                key: SourceStatement.from_dict(value)
                for key, value in data.get("source_statements", {}).items()
            },
            consultations={
                key: ConsultationResult.from_dict(value)
                for key, value in data.get("consultations", {}).items()
            },
            source_groups={
                key: SourceGroup.from_dict(value)
                for key, value in data.get("source_groups", {}).items()
            },
            conflicts={
                key: ClaimConflict.from_dict(value)
                for key, value in data.get("conflicts", {}).items()
            },
            comparisons={
                key: ComparisonResult.from_dict(value)
                for key, value in data.get("comparisons", {}).items()
            },
            schema_version=max(3, int(data.get("schema_version", 1))),
        )
        for statement in knowledge.source_statements.values():
            knowledge._register_source_group(statement)
        for claim in knowledge.known_claims.values():
            if not claim.source_groups:
                claim.source_groups.extend(
                    source_group_id(root_id)
                    for root_id in claim.source_record_roots)
            for root_id, group_id in zip(
                    claim.source_record_roots, claim.source_groups):
                knowledge._ensure_source_group(
                    group_id, "record_lineage", root_id)
        knowledge._mark_contradictions()
        return knowledge


def stable_conflict_id(first_key: str, second_key: str,
                       overlap_range: tuple[int, int]) -> str:
    first_key, second_key = sorted((first_key, second_key))
    return stable_investigation_id(
        "conflict", (
            first_key, second_key,
            str(overlap_range[0]), str(overlap_range[1]),
        ))
