"""Player-owned claims reconstructed from evidence, never from event truth."""

from __future__ import annotations

from dataclasses import dataclass, field

from game.investigation import ConsultationResult, SourceStatement


STATUS_THRESHOLDS = (
    (0.82, "高度可信"),
    (0.62, "可信"),
    (0.42, "可能"),
    (0.0, "传闻"),
)


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
    supporting_statement_ids: list[str] = field(default_factory=list)
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
            "supporting_statement_ids": list(
                self.supporting_statement_ids),
            "base_confidence": self.base_confidence,
            "confidence": self.confidence,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnownClaim":
        time_range = data.get("time_range", [0, 0])
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
            source_record_roots=list(data.get("source_record_roots", [])),
            supporting_statement_ids=list(data.get(
                "supporting_statement_ids", [])),
            base_confidence=float(data.get(
                "base_confidence", data.get("confidence", 0.0))),
            confidence=float(data.get("confidence", 0.0)),
            status=data.get("status", "传闻"),
        )


@dataclass
class PlayerKnowledge:
    discovered_evidence_ids: set[str] = field(default_factory=set)
    known_claims: dict[str, KnownClaim] = field(default_factory=dict)
    source_statements: dict[str, SourceStatement] = field(default_factory=dict)
    consultations: dict[str, ConsultationResult] = field(default_factory=dict)

    def discover_evidence(self, evidence_id: str) -> None:
        self.discovered_evidence_ids.add(evidence_id)

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
        learned = []
        for statement in result.statements:
            if statement.id in self.source_statements:
                continue
            self.source_statements[statement.id] = statement
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
        known.time_range = (
            min(known.time_range[0], claim.time_range[0]),
            max(known.time_range[1], claim.time_range[1]),
        )
        self._recompute_confidence_values(
            known,
            statement.perspective,
            statement.carrier_condition,
            statement.comprehension,
            statement.expertise_bonus,
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
        known.time_range = (
            min(known.time_range[0], claim.time_range[0]),
            max(known.time_range[1], claim.time_range[1]),
        )
        self._recompute_confidence(
            known, record.perspective, evidence, comprehension,
            expertise_bonus)
        return known

    def _mark_contradictions(self) -> None:
        claims = list(self.known_claims.values())
        for claim in claims:
            claim.contradicting_evidence_ids = []
        for index, first in enumerate(claims):
            for second in claims[index + 1:]:
                if (first.topic_key() != second.topic_key()
                        or first.object == second.object):
                    continue
                for evidence_id in second.supporting_evidence_ids:
                    if evidence_id not in first.contradicting_evidence_ids:
                        first.contradicting_evidence_ids.append(evidence_id)
                for evidence_id in first.supporting_evidence_ids:
                    if evidence_id not in second.contradicting_evidence_ids:
                        second.contradicting_evidence_ids.append(evidence_id)
        for claim in claims:
            penalty = 0.12 if claim.contradicting_evidence_ids else 0.0
            claim.confidence = max(0.05, claim.base_confidence - penalty)
            claim.status = self._status_for(claim.confidence)

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
        reliability = {
            "scholarly": 0.14,
            "merchant": 0.12,
            "eyewitness": 0.10,
            "official": 0.08,
            "author": 0.08,
            "opposition": 0.06,
            "folk": 0.03,
        }.get(perspective, 0.05)
        independent_sources = len(known.source_record_roots)
        confidence = (
            0.18 + reliability
            + 0.16 * min(independent_sources, 3)
            + 0.12 * max(0.0, min(1.0, condition))
            + 0.10 * max(0.0, min(1.0, comprehension + expertise_bonus))
        )
        # Copies of one record improve legibility, not source independence.
        confidence += 0.02 * min(len(known.supporting_evidence_ids) - 1, 2)
        known.base_confidence = min(0.95, confidence)
        known.confidence = known.base_confidence
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

    def to_dict(self) -> dict:
        return {
            "discovered_evidence_ids": sorted(self.discovered_evidence_ids),
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerKnowledge":
        return cls(
            discovered_evidence_ids=set(
                data.get("discovered_evidence_ids", [])),
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
        )
