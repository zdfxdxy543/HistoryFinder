"""Truth-isolated data exchanged by investigation services and UIs."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable


EVIDENCE_DOMAIN_BY_SUBTYPE = {
    "battlefield_ruins": ("warfare", "architecture"),
    "scattered_weapons": ("warfare", "craftsmanship"),
    "war_record": ("warfare", "administration"),
    "war_song": ("warfare", "local_history"),
    "burn_layer": ("disaster", "architecture"),
    "flood_sediment": ("disaster", "natural_history"),
    "damaged_relics": ("disaster", "craftsmanship"),
    "survivor_account": ("disaster", "local_history"),
    "repaired_masonry": ("architecture", "craftsmanship"),
    "reconstruction_account": ("architecture", "administration"),
    "reused_fittings": ("architecture", "craftsmanship"),
    "relief_inventory": ("trade", "administration"),
    "supply_crate_remains": ("trade", "craftsmanship"),
    "relief_story": ("trade", "local_history"),
    "abandoned_dwellings": ("architecture", "local_history"),
    "occupation_gap": ("architecture", "natural_history"),
    "exodus_memory": ("local_history",),
    "research_notes": ("natural_philosophy", "paleography"),
    "crafted_item": ("natural_philosophy", "craftsmanship"),
    "literary_manuscript": ("literature", "paleography"),
    "literary_commentary": ("literature", "paleography"),
    "popular_recitation": ("literature", "local_history"),
    "traveling_literary_copy": ("literature", "paleography"),
    "adapted_recitation": ("literature", "local_history"),
    "theoretical_treatise": ("natural_philosophy", "paleography"),
    "lecture_notes": ("natural_philosophy", "paleography"),
    "demonstration_model": ("natural_philosophy", "craftsmanship"),
    "temple": ("religion", "architecture"),
    "religious_text": ("religion", "paleography"),
    "hymn": ("religion", "local_history"),
    "burned_structures": ("warfare", "architecture"),
    "raid_story": ("warfare", "local_history"),
    "treaty_tablet": ("diplomacy", "administration"),
    "treaty_pillar": ("diplomacy", "architecture"),
    "oath_of_peace": ("diplomacy", "local_history"),
    "damaged_buildings": ("warfare", "architecture"),
    "rebel_manifesto": ("politics", "administration"),
    "rebellion_story": ("politics", "local_history"),
    "building_remains": ("architecture",),
    "construction_record": ("architecture", "administration"),
    "builders_tools": ("architecture", "craftsmanship"),
    "trade_ledger": ("trade", "administration"),
    "foreign_coin": ("trade", "craftsmanship"),
    "merchant_tale": ("trade", "local_history"),
    "succession_decree": ("politics", "administration"),
    "ruler_tomb": ("politics", "architecture"),
    "succession_gossip": ("politics", "local_history"),
    "census_record": ("administration", "demography"),
    "old_timers_memory": ("demography", "local_history"),
    "tax_record": ("trade", "administration"),
    "grain_storage_jar": ("trade", "craftsmanship"),
    "traders_complaint": ("trade", "local_history"),
    "festival_token": ("festival", "craftsmanship"),
    "festival_song": ("festival", "local_history"),
    "birth_record": ("genealogy", "administration"),
    "birth_story": ("genealogy", "local_history"),
    "trial_record": ("law", "administration"),
    "crime_gossip": ("law", "local_history"),
    "marriage_contract": ("genealogy", "administration"),
    "wedding_tale": ("genealogy", "local_history"),
    "exploration_journal": ("travel", "paleography"),
    "explorers_tale": ("travel", "local_history"),
    "omen_record": ("astronomy", "religion"),
    "omen_story": ("astronomy", "local_history"),
    "duel_story": ("warfare", "local_history"),
    "duel_weapon": ("warfare", "craftsmanship"),
    "founding_charter": ("administration", "local_history"),
    "foundation_stone": ("architecture", "local_history"),
    "founding_legend": ("local_history",),
}


PREDICATE_DOMAINS = {
    "war_result": ("warfare",),
    "rebellion_result": ("politics",),
    "authored_work": ("literature",),
    "work_circulated": ("literature",),
    "authored_treatise": ("natural_philosophy",),
    "reported_discovery": ("natural_philosophy", "craftsmanship"),
    "suffered_disaster": ("disaster",),
    "built": ("architecture",),
    "opened_trade_route": ("trade",),
}


def _base_subtype(subtype: str, is_copy: bool = False) -> str:
    if is_copy and subtype.endswith("_copy"):
        return subtype[:-5]
    return subtype


def domains_for_evidence(subtype: str, evidence_type: str,
                         is_copy: bool = False) -> tuple[str, ...]:
    base = _base_subtype(subtype, is_copy)
    configured = EVIDENCE_DOMAIN_BY_SUBTYPE.get(base)
    if configured:
        return configured
    fallback = {
        "document": ("paleography",),
        "oral": ("local_history",),
        "artifact": ("craftsmanship",),
        "structure": ("architecture",),
        "environmental": ("natural_history",),
    }
    return fallback.get(evidence_type, ("unknown",))


def domains_for_predicate(predicate: str) -> tuple[str, ...]:
    configured = PREDICATE_DOMAINS.get(predicate)
    if configured:
        return configured
    if predicate.startswith("reported_"):
        topic = predicate.removeprefix("reported_")
        return {
            "raid": ("warfare",),
            "treaty": ("diplomacy",),
            "economic": ("trade",),
            "festival": ("festival",),
            "notable_birth": ("genealogy",),
            "crime": ("law",),
            "marriage": ("genealogy",),
            "exploration": ("travel",),
            "omen": ("astronomy",),
            "duel": ("warfare",),
            "founding": ("local_history",),
            "ruler_change": ("politics",),
            "decline": ("local_history",),
        }.get(topic, ("local_history",))
    return ("local_history",)


@dataclass(frozen=True)
class ClaimView:
    """A claim retained by a carrier, without its truth-side provenance."""

    subject: str
    predicate: str
    object: str
    statement_cn: str
    time_range: tuple[int, int]
    qualifiers: tuple[str, ...] = ()

    @classmethod
    def from_claim(cls, claim) -> "ClaimView":
        return cls(
            subject=claim.subject,
            predicate=claim.predicate,
            object=claim.object,
            statement_cn=claim.statement_cn,
            time_range=tuple(claim.time_range),
            qualifiers=tuple(claim.qualifiers),
        )

    def semantic_key(self) -> str:
        return f"{self.subject}|{self.predicate}|{self.object}"

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "statement_cn": self.statement_cn,
            "time_range": list(self.time_range),
            "qualifiers": list(self.qualifiers),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimView":
        time_range = data.get("time_range", [0, 0])
        return cls(
            subject=data.get("subject", "未知对象"),
            predicate=data.get("predicate", "unknown"),
            object=data.get("object", "unknown"),
            statement_cn=data.get("statement_cn", "主张内容不明。"),
            time_range=(int(time_range[0]), int(time_range[1])),
            qualifiers=tuple(data.get("qualifiers", [])),
        )


@dataclass(frozen=True)
class EvidencePublicView:
    """Evidence properties that an investigation service may inspect."""

    id: str
    observed_name: str
    evidence_type: str
    material: str
    state: str
    condition: float
    location_id: str
    tags: tuple[str, ...]
    analysis_domains: tuple[str, ...]

    @classmethod
    def from_evidence(cls, evidence) -> "EvidencePublicView":
        condition = (
            evidence.current_durability / evidence.max_durability
            if evidence.max_durability > 0 else 0.0)
        return cls(
            id=evidence.id,
            observed_name=evidence.physical_features.get(
                "display_name", evidence.subtype.replace("_", " ")),
            evidence_type=evidence.evidence_type,
            material=evidence.material,
            state=evidence.state,
            condition=max(0.0, min(1.0, condition)),
            location_id=evidence.location_id,
            tags=tuple(evidence.physical_features.get("tags", [])),
            analysis_domains=domains_for_evidence(
                evidence.subtype, evidence.evidence_type,
                is_copy=bool(evidence.is_copy_of)),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "observed_name": self.observed_name,
            "evidence_type": self.evidence_type,
            "material": self.material,
            "state": self.state,
            "condition": self.condition,
            "location_id": self.location_id,
            "tags": list(self.tags),
            "analysis_domains": list(self.analysis_domains),
        }


@dataclass(frozen=True)
class Observation:
    """One player-visible property, without historical interpretation."""

    id: str
    evidence_id: str
    observation_type: str
    value: str
    description_cn: str
    method: str
    clarity: float
    observed_at_location_id: str
    observed_by: str = "player"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "observation_type": self.observation_type,
            "value": self.value,
            "description_cn": self.description_cn,
            "method": self.method,
            "clarity": self.clarity,
            "observed_at_location_id": self.observed_at_location_id,
            "observed_by": self.observed_by,
        }

    @classmethod
    def create(cls, evidence: EvidencePublicView, observation_type: str,
               value: str, description_cn: str, method: str = "visual",
               clarity: float | None = None) -> "Observation":
        clarity = evidence.condition if clarity is None else clarity
        return cls(
            id=stable_investigation_id(
                "observation", (
                    evidence.id, observation_type, value, method,
                    evidence.location_id,
                )),
            evidence_id=evidence.id,
            observation_type=observation_type,
            value=value,
            description_cn=description_cn,
            method=method,
            clarity=max(0.0, min(1.0, clarity)),
            observed_at_location_id=evidence.location_id,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Observation":
        return cls(
            id=data["id"],
            evidence_id=data.get("evidence_id", ""),
            observation_type=data.get("observation_type", "unknown"),
            value=data.get("value", "unknown"),
            description_cn=data.get("description_cn", "观察内容不明。"),
            method=data.get("method", "visual"),
            clarity=float(data.get("clarity", 0.0)),
            observed_at_location_id=data.get(
                "observed_at_location_id", ""),
            observed_by=data.get("observed_by", "player"),
        )


@dataclass(frozen=True)
class DocumentReading:
    """The exact text fragments exposed to the player by one read action."""

    id: str
    evidence_id: str
    status: str
    language_code: str
    readability: float
    visible_passages: tuple[str, ...]
    read_at_location_id: str

    @classmethod
    def from_result(cls, evidence_id: str, location_id: str,
                    result: dict) -> "DocumentReading":
        passages = tuple(result.get("visible_passages", ()))
        status = result.get("status", "no_text")
        language = result.get("language_code", "unknown")
        readability = float(result.get("readability", 0.0))
        return cls(
            id=stable_investigation_id(
                "reading", (
                    evidence_id, location_id, status, language,
                    f"{readability:.6f}", *passages,
                )),
            evidence_id=evidence_id,
            status=status,
            language_code=language,
            readability=max(0.0, min(1.0, readability)),
            visible_passages=passages,
            read_at_location_id=location_id,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "status": self.status,
            "language_code": self.language_code,
            "readability": self.readability,
            "visible_passages": list(self.visible_passages),
            "read_at_location_id": self.read_at_location_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentReading":
        return cls(
            id=data["id"],
            evidence_id=data.get("evidence_id", ""),
            status=data.get("status", "no_text"),
            language_code=data.get("language_code", "unknown"),
            readability=float(data.get("readability", 0.0)),
            visible_passages=tuple(data.get("visible_passages", ())),
            read_at_location_id=data.get("read_at_location_id", ""),
        )


@dataclass
class SourceGroup:
    """One independent lineage shared by copies or oral transmissions."""

    id: str
    group_type: str
    root_record_id: str
    evidence_ids: list[str] = field(default_factory=list)
    statement_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "group_type": self.group_type,
            "root_record_id": self.root_record_id,
            "evidence_ids": list(self.evidence_ids),
            "statement_ids": list(self.statement_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceGroup":
        return cls(
            id=data["id"],
            group_type=data.get("group_type", "record_lineage"),
            root_record_id=data.get("root_record_id", ""),
            evidence_ids=list(data.get("evidence_ids", ())),
            statement_ids=list(data.get("statement_ids", ())),
        )


@dataclass(frozen=True)
class RecordPublicView:
    """Carrier-retained record claims with all event links removed."""

    id: str
    source_root_id: str
    perspective: str
    language_code: str
    record_type: str
    carrier_subtype: str
    claims: tuple[ClaimView, ...]
    source_group_id: str = ""

    @classmethod
    def from_record_and_evidence(cls, record, evidence) -> "RecordPublicView":
        retained = set(evidence.retained_claim_ids)
        claims = tuple(
            ClaimView.from_claim(claim)
            for claim in record.claimed_facts
            if claim.id in retained
        )
        root_id = record.copy_parent_id or record.id
        return cls(
            id=record.id,
            source_root_id=root_id,
            perspective=record.perspective,
            language_code=record.language_code,
            record_type=record.record_type,
            carrier_subtype=record.carrier_subtype,
            claims=claims,
            source_group_id=source_group_id(root_id),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_root_id": self.source_root_id,
            "perspective": self.perspective,
            "language_code": self.language_code,
            "record_type": self.record_type,
            "carrier_subtype": self.carrier_subtype,
            "claims": [claim.to_dict() for claim in self.claims],
            "source_group_id": self.source_group_id,
        }


@dataclass(frozen=True)
class ReadingPublicView:
    status: str
    language_code: str = "unknown"
    readability: float = 0.0

    @classmethod
    def from_result(cls, result: dict) -> "ReadingPublicView":
        return cls(
            status=result.get("status", "no_text"),
            language_code=result.get("language_code", "unknown"),
            readability=float(result.get("readability", 0.0)),
        )


@dataclass(frozen=True)
class ConsultantView:
    id: str
    name: str
    role: str
    expertise: tuple[tuple[str, float], ...]
    known_languages: tuple[str, ...] = ("common",)

    def expertise_for(self, domain: str) -> float:
        return dict(self.expertise).get(domain, 0.0)

    @classmethod
    def scholar(cls, person) -> "ConsultantView":
        role_domains = {
            "scholar": {
                "paleography": 0.78,
                "natural_philosophy": 0.70,
                "literature": 0.62,
                "administration": 0.42,
            },
            "scribe": {
                "paleography": 0.72,
                "administration": 0.68,
                "literature": 0.46,
            },
            "writer": {
                "literature": 0.70,
                "paleography": 0.52,
                "local_history": 0.40,
            },
        }
        combined: dict[str, float] = {}
        for role in sorted(person.roles):
            for domain, value in role_domains.get(role, {}).items():
                combined[domain] = max(combined.get(domain, 0.0), value)
        return cls(
            id=person.id,
            name=person.name,
            role="scholar",
            expertise=tuple(sorted(combined.items())),
        )

    @classmethod
    def local_community(cls, location_id: str) -> "ConsultantView":
        return cls(
            id=f"community:{location_id}",
            name="当地居民",
            role="villager",
            expertise=(("local_history", 0.62),),
        )

    @classmethod
    def from_informant(cls, informant, person,
                       role_override: str | None = None) -> "ConsultantView":
        known_languages = tuple(sorted(
            language for language, proficiency
            in informant.language_proficiency.items()
            if proficiency >= 0.50
        ))
        return cls(
            id=informant.id,
            name=person.name,
            role=role_override or informant.role,
            expertise=tuple(sorted(informant.expertise.items())),
            known_languages=known_languages,
        )


@dataclass(frozen=True)
class OralKnowledgeView:
    """A local oral carrier available to a community, without event links."""

    evidence_id: str
    location_id: str
    condition: float
    domains: tuple[str, ...]
    record: RecordPublicView

    @classmethod
    def from_record_and_evidence(cls, record, evidence) -> "OralKnowledgeView":
        public_record = RecordPublicView.from_record_and_evidence(
            record, evidence)
        claim_domains = {
            domain
            for claim in public_record.claims
            for domain in domains_for_predicate(claim.predicate)
        }
        evidence_domains = set(domains_for_evidence(
            evidence.subtype, evidence.evidence_type,
            is_copy=bool(evidence.is_copy_of)))
        condition = (
            evidence.current_durability / evidence.max_durability
            if evidence.max_durability > 0 else 0.0)
        return cls(
            evidence_id=evidence.id,
            location_id=evidence.location_id,
            condition=max(0.0, min(1.0, condition)),
            domains=tuple(sorted(claim_domains | evidence_domains)),
            record=public_record,
        )


@dataclass(frozen=True)
class HeldKnowledgeView:
    """One persisted knowledge entry exposed without truth-side links."""

    entry_id: str
    holder_id: str
    entry_type: str
    source_evidence_id: str
    location_ids: tuple[str, ...]
    certainty: float
    transmission_depth: int
    domains: tuple[str, ...]
    record: RecordPublicView

    @classmethod
    def from_entry_record_and_evidence(
            cls, entry, record, evidence) -> "HeldKnowledgeView":
        retained = set(evidence.retained_claim_ids)
        allowed = set(entry.claim_ids)
        claims = tuple(
            ClaimView.from_claim(claim)
            for claim in record.claimed_facts
            if claim.id in retained and claim.id in allowed
        )
        public_record = RecordPublicView(
            id=record.id,
            source_root_id=entry.source_root_id,
            perspective=record.perspective,
            language_code=record.language_code,
            record_type=record.record_type,
            carrier_subtype=record.carrier_subtype,
            claims=claims,
            source_group_id=source_group_id(entry.source_root_id),
        )
        claim_domains = {
            domain
            for claim in claims
            for domain in domains_for_predicate(claim.predicate)
        }
        carrier_domains = set(domains_for_evidence(
            evidence.subtype, evidence.evidence_type,
            is_copy=bool(evidence.is_copy_of)))
        return cls(
            entry_id=entry.id,
            holder_id=entry.holder_id,
            entry_type=entry.entry_type,
            source_evidence_id=entry.source_evidence_id,
            location_ids=tuple(entry.location_ids),
            certainty=max(0.0, min(1.0, entry.certainty)),
            transmission_depth=entry.transmission_depth,
            domains=tuple(sorted(claim_domains | carrier_domains)),
            record=public_record,
        )


@dataclass(frozen=True)
class SourceStatement:
    id: str
    speaker_type: str
    speaker_id: str
    presented_evidence_id: str
    source_evidence_id: str | None
    source_record_root_id: str | None
    statement_type: str
    statement_cn: str
    basis_codes: tuple[str, ...] = ()
    uncertainty_codes: tuple[str, ...] = ()
    claim: ClaimView | None = None
    perspective: str = "unknown"
    carrier_condition: float = 0.0
    comprehension: float = 0.0
    expertise_bonus: float = 0.0
    source_group_id: str | None = None
    source_group_type: str = "record_lineage"
    transmission_depth: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "speaker_type": self.speaker_type,
            "speaker_id": self.speaker_id,
            "presented_evidence_id": self.presented_evidence_id,
            "source_evidence_id": self.source_evidence_id,
            "source_record_root_id": self.source_record_root_id,
            "statement_type": self.statement_type,
            "statement_cn": self.statement_cn,
            "basis_codes": list(self.basis_codes),
            "uncertainty_codes": list(self.uncertainty_codes),
            "claim": self.claim.to_dict() if self.claim else None,
            "perspective": self.perspective,
            "carrier_condition": self.carrier_condition,
            "comprehension": self.comprehension,
            "expertise_bonus": self.expertise_bonus,
            "source_group_id": self.source_group_id,
            "source_group_type": self.source_group_type,
            "transmission_depth": self.transmission_depth,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceStatement":
        claim_data = data.get("claim")
        root_id = data.get("source_record_root_id")
        return cls(
            id=data["id"],
            speaker_type=data.get("speaker_type", "unknown"),
            speaker_id=data.get("speaker_id", "unknown"),
            presented_evidence_id=data.get("presented_evidence_id", ""),
            source_evidence_id=data.get("source_evidence_id"),
            source_record_root_id=root_id,
            statement_type=data.get("statement_type", "limitation"),
            statement_cn=data.get("statement_cn", ""),
            basis_codes=tuple(data.get("basis_codes", [])),
            uncertainty_codes=tuple(data.get("uncertainty_codes", [])),
            claim=ClaimView.from_dict(claim_data) if claim_data else None,
            perspective=data.get("perspective", "unknown"),
            carrier_condition=float(data.get("carrier_condition", 0.0)),
            comprehension=float(data.get("comprehension", 0.0)),
            expertise_bonus=float(data.get("expertise_bonus", 0.0)),
            source_group_id=data.get("source_group_id") or (
                source_group_id(root_id) if root_id else None),
            source_group_type=data.get(
                "source_group_type", "record_lineage"),
            transmission_depth=max(
                0, int(data.get("transmission_depth", 0))),
        )


@dataclass(frozen=True)
class ConsultationResult:
    id: str
    consultant_id: str
    consultant_name: str
    consultant_role: str
    evidence_id: str
    statements: tuple[SourceStatement, ...] = ()
    notes_cn: tuple[str, ...] = ()
    matched_knowledge_ids: tuple[str, ...] = ()

    @property
    def claim_statements(self) -> tuple[SourceStatement, ...]:
        return tuple(item for item in self.statements if item.claim is not None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "consultant_id": self.consultant_id,
            "consultant_name": self.consultant_name,
            "consultant_role": self.consultant_role,
            "evidence_id": self.evidence_id,
            "statements": [item.to_dict() for item in self.statements],
            "notes_cn": list(self.notes_cn),
            "matched_knowledge_ids": list(self.matched_knowledge_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsultationResult":
        return cls(
            id=data["id"],
            consultant_id=data.get("consultant_id", "unknown"),
            consultant_name=data.get("consultant_name", "未知咨询者"),
            consultant_role=data.get("consultant_role", "unknown"),
            evidence_id=data.get("evidence_id", ""),
            statements=tuple(
                SourceStatement.from_dict(item)
                for item in data.get("statements", [])),
            notes_cn=tuple(data.get("notes_cn", [])),
            matched_knowledge_ids=tuple(
                data.get("matched_knowledge_ids", [])),
        )


@dataclass(frozen=True)
class ClaimConflict:
    """A strong, unresolved conflict derived from player-owned claims."""

    id: str
    first_claim_key: str
    second_claim_key: str
    relation_type: str
    strength: str
    overlap_range: tuple[int, int]
    first_statement_ids: tuple[str, ...] = ()
    second_statement_ids: tuple[str, ...] = ()
    reason_cn: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "first_claim_key": self.first_claim_key,
            "second_claim_key": self.second_claim_key,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "overlap_range": list(self.overlap_range),
            "first_statement_ids": list(self.first_statement_ids),
            "second_statement_ids": list(self.second_statement_ids),
            "reason_cn": self.reason_cn,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimConflict":
        overlap = data.get("overlap_range", [0, 0])
        return cls(
            id=data["id"],
            first_claim_key=data.get("first_claim_key", ""),
            second_claim_key=data.get("second_claim_key", ""),
            relation_type=data.get("relation_type", "exclusive"),
            strength=data.get("strength", "strong"),
            overlap_range=(int(overlap[0]), int(overlap[1])),
            first_statement_ids=tuple(data.get("first_statement_ids", ())),
            second_statement_ids=tuple(data.get("second_statement_ids", ())),
            reason_cn=data.get("reason_cn", ""),
        )


@dataclass(frozen=True)
class ComparisonResult:
    """A deterministic comparison of player-observable evidence properties."""

    id: str
    evidence_ids: tuple[str, str]
    method: str
    similarities_cn: tuple[str, ...] = ()
    differences_cn: tuple[str, ...] = ()
    limitations_cn: tuple[str, ...] = ()
    source_group_relation: str = "unknown"
    observation_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "evidence_ids": list(self.evidence_ids),
            "method": self.method,
            "similarities_cn": list(self.similarities_cn),
            "differences_cn": list(self.differences_cn),
            "limitations_cn": list(self.limitations_cn),
            "source_group_relation": self.source_group_relation,
            "observation_ids": list(self.observation_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonResult":
        evidence_ids = data.get("evidence_ids", ["", ""])
        return cls(
            id=data["id"],
            evidence_ids=(evidence_ids[0], evidence_ids[1]),
            method=data.get("method", "visual"),
            similarities_cn=tuple(data.get("similarities_cn", ())),
            differences_cn=tuple(data.get("differences_cn", ())),
            limitations_cn=tuple(data.get("limitations_cn", ())),
            source_group_relation=data.get(
                "source_group_relation", "unknown"),
            observation_ids=tuple(data.get("observation_ids", ())),
        )


def stable_investigation_id(prefix: str, parts: Iterable[str]) -> str:
    payload = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}_{digest}"


def source_group_id(root_record_id: str) -> str:
    """Return a stable public ID for one record or oral lineage."""
    return stable_investigation_id("source_group", (root_record_id,))


def build_reading_statements(
        evidence: EvidencePublicView, reading: DocumentReading,
        record: RecordPublicView | None) -> tuple[SourceStatement, ...]:
    """Turn a readable carrier into sourced claims without consulting truth."""
    if (reading.status != "readable" or record is None
            or reading.readability < 0.20):
        return ()
    count = max(1, round(len(record.claims) * reading.readability))
    statements = []
    group_type = (
        "oral_tradition" if record.record_type == "oral_tradition"
        else "record_lineage")
    for index, claim in enumerate(record.claims[:count], 1):
        statements.append(SourceStatement(
            id=stable_investigation_id(
                "statement", (reading.id, str(index), claim.semantic_key())),
            speaker_type="player_reading",
            speaker_id="player",
            presented_evidence_id=evidence.id,
            source_evidence_id=evidence.id,
            source_record_root_id=record.source_root_id,
            statement_type="document_transcription",
            statement_cn=f"文书中可辨认的一项说法是：{claim.statement_cn}",
            basis_codes=("visible_text", "retained_claim"),
            uncertainty_codes=("record_claim_not_truth",),
            claim=claim,
            perspective=record.perspective,
            carrier_condition=evidence.condition,
            comprehension=reading.readability,
            source_group_id=(record.source_group_id
                             or source_group_id(record.source_root_id)),
            source_group_type=group_type,
            transmission_depth=(1 if record.id != record.source_root_id else 0),
        ))
    return tuple(statements)
