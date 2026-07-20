"""Perspective-bound historical records produced from simulation events."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class Claim:
    """A proposition asserted by a record, not simulation truth."""

    id: str
    subject: str
    predicate: str
    object: str
    statement_cn: str
    time_range: tuple[int, int]
    qualifiers: list[str] = field(default_factory=list)
    schema_version: int = 1

    def semantic_key(self) -> str:
        return f"{self.subject}|{self.predicate}|{self.object}"

    def topic_key(self) -> str:
        return f"{self.subject}|{self.predicate}"

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "statement_cn": self.statement_cn,
            "time_range": list(self.time_range),
            "qualifiers": list(self.qualifiers),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Claim":
        time_range = data.get("time_range", [0, 0])
        return cls(
            id=data["id"],
            subject=data.get("subject", "未知对象"),
            predicate=data.get("predicate", "unknown"),
            object=data.get("object", "unknown"),
            statement_cn=data.get("statement_cn", "记录内容不明。"),
            time_range=(int(time_range[0]), int(time_range[1])),
            qualifiers=list(data.get("qualifiers", [])),
            schema_version=data.get("schema_version", 1),
        )


@dataclass
class HistoricalRecord:
    """What an author or institution claimed about one or more events."""

    id: str
    source_event_ids: list[str]
    created_year: int
    created_location_id: str
    record_type: str
    claimed_facts: list[Claim]
    perspective: str
    intended_audience: str
    carrier_subtype: str
    author_person_id: str | None = None
    author_faction_id: str | None = None
    omitted_facts: list[str] = field(default_factory=list)
    distortions: list[str] = field(default_factory=list)
    secrecy: float = 0.0
    copy_parent_id: str | None = None
    language_code: str = "common"
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source_event_ids": list(self.source_event_ids),
            "author_person_id": self.author_person_id,
            "author_faction_id": self.author_faction_id,
            "created_year": self.created_year,
            "created_location_id": self.created_location_id,
            "record_type": self.record_type,
            "claimed_facts": [claim.to_dict() for claim in self.claimed_facts],
            "omitted_facts": list(self.omitted_facts),
            "distortions": list(self.distortions),
            "perspective": self.perspective,
            "intended_audience": self.intended_audience,
            "secrecy": self.secrecy,
            "copy_parent_id": self.copy_parent_id,
            "language_code": self.language_code,
            "carrier_subtype": self.carrier_subtype,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricalRecord":
        return cls(
            id=data["id"],
            source_event_ids=list(data.get("source_event_ids", [])),
            author_person_id=data.get("author_person_id"),
            author_faction_id=data.get("author_faction_id"),
            created_year=data.get("created_year", 0),
            created_location_id=data.get("created_location_id", ""),
            record_type=data.get("record_type", "unknown"),
            claimed_facts=[
                Claim.from_dict(item)
                for item in data.get("claimed_facts", [])
            ],
            omitted_facts=list(data.get("omitted_facts", [])),
            distortions=list(data.get("distortions", [])),
            perspective=data.get("perspective", "unknown"),
            intended_audience=data.get("intended_audience", "public"),
            secrecy=data.get("secrecy", 0.0),
            copy_parent_id=data.get("copy_parent_id"),
            language_code=data.get("language_code", "common"),
            carrier_subtype=data.get("carrier_subtype", "unknown"),
            schema_version=data.get("schema_version", 1),
        )


RECORD_TYPES = {
    "founding_charter": "charter",
    "war_record": "military_report",
    "survivor_account": "eyewitness_account",
    "rebel_manifesto": "manifesto",
    "tax_record": "ledger",
    "trade_ledger": "ledger",
    "relief_receipt": "receipt",
    "treaty_tablet": "treaty",
    "literary_manuscript": "literary_work",
    "literary_commentary": "commentary",
    "traveling_literary_copy": "literary_copy",
    "theoretical_treatise": "treatise",
    "lecture_notes": "lecture_notes",
    "research_notes": "research_notes",
    "popular_recitation": "recitation",
    "adapted_recitation": "recitation",
}


class RecordGenerator:
    """Build deterministic, perspective-limited records for evidence recipes."""

    def __init__(self, seed: int):
        self.seed = seed
        self.counter = 0

    def _next_id(self) -> str:
        self.counter += 1
        return f"record_{self.counter:06d}"

    def create_records_for_event(self, event, recipes: list[dict],
                                 settlements: dict, persons: dict
                                 ) -> dict[str, list[HistoricalRecord]]:
        records = {}
        for recipe in recipes:
            if recipe["type"] not in {"document", "oral"}:
                continue
            subtype = recipe["subtype"]
            original = self._create_record(
                event, subtype, recipe["type"], settlements, persons)
            records[subtype] = [original]
            for copy_index in range(recipe.get("copies", 0)):
                records[subtype].append(
                    self._create_copy(original, copy_index))
        return records

    def _create_copy(self, parent: HistoricalRecord,
                     copy_index: int) -> HistoricalRecord:
        record_id = self._next_id()
        payload = (
            f"{self.seed}|{parent.id}|copy|{copy_index}".encode("utf-8"))
        stable_value = int(hashlib.sha256(payload).hexdigest()[:8], 16)
        year_offset = 1 + stable_value % 10
        claims = [
            Claim(
                id=f"{record_id}:claim:{index}",
                subject=claim.subject,
                predicate=claim.predicate,
                object=claim.object,
                statement_cn=claim.statement_cn,
                time_range=claim.time_range,
                qualifiers=list(claim.qualifiers) + ["copied_text"],
            )
            for index, claim in enumerate(parent.claimed_facts, 1)
        ]
        distortions = list(parent.distortions) + ["copyist_variation"]
        return HistoricalRecord(
            id=record_id,
            source_event_ids=list(parent.source_event_ids),
            author_person_id=parent.author_person_id,
            author_faction_id=parent.author_faction_id,
            created_year=parent.created_year + year_offset,
            created_location_id=parent.created_location_id,
            record_type=parent.record_type,
            claimed_facts=claims,
            omitted_facts=list(parent.omitted_facts),
            distortions=distortions,
            perspective=parent.perspective,
            intended_audience=parent.intended_audience,
            secrecy=parent.secrecy,
            copy_parent_id=parent.id,
            language_code=parent.language_code,
            carrier_subtype=parent.carrier_subtype,
        )

    def _create_record(self, event, subtype: str, evidence_type: str,
                       settlements: dict, persons: dict) -> HistoricalRecord:
        record_id = self._next_id()
        perspective = self._perspective(subtype, evidence_type)
        author_person_id = self._select_author(event, perspective, persons)
        author_faction_id = None if author_person_id else event.primary_location
        claims, distortions, omitted = self._build_claims(
            record_id, event, perspective, settlements)
        audience = {
            "official": "administrators",
            "opposition": "supporters",
            "merchant": "account_holders",
            "scholarly": "students_and_craftspeople",
            "author": "readers_and_listeners",
            "eyewitness": "local_community",
            "folk": "local_community",
        }.get(perspective, "public")
        secrecy = 0.35 if subtype in {"private_letter", "research_notes"} else 0.0
        return HistoricalRecord(
            id=record_id,
            source_event_ids=[event.id],
            author_person_id=author_person_id,
            author_faction_id=author_faction_id,
            created_year=event.year,
            created_location_id=event.primary_location,
            record_type=RECORD_TYPES.get(
                subtype, "oral_tradition" if evidence_type == "oral" else "record"),
            claimed_facts=claims,
            omitted_facts=omitted,
            distortions=distortions,
            perspective=perspective,
            intended_audience=audience,
            secrecy=secrecy,
            carrier_subtype=subtype,
        )

    def _perspective(self, subtype: str, evidence_type: str) -> str:
        if evidence_type == "oral":
            return "folk"
        if subtype in {"rebel_manifesto"}:
            return "opposition"
        if subtype in {"trade_ledger", "tax_record", "relief_receipt"}:
            return "merchant"
        if subtype in {"theoretical_treatise", "lecture_notes", "research_notes"}:
            return "scholarly"
        if subtype in {"literary_manuscript", "literary_commentary",
                       "traveling_literary_copy"}:
            return "author"
        if subtype in {"survivor_account", "private_letter"}:
            return "eyewitness"
        return "official"

    def _select_author(self, event, perspective: str, persons: dict) -> str | None:
        preferred_roles = {
            "official": {"ruler", "diplomat", "scribe"},
            "opposition": {"rebel_leader"},
            "scholarly": {"scholar"},
            "author": {"writer", "scribe"},
            "eyewitness": {"general", "scribe"},
        }.get(perspective, set())
        candidates = [
            persons[person_id] for person_id in event.person_ids
            if person_id in persons
        ]
        for person in candidates:
            if preferred_roles.intersection(person.roles):
                return person.id
        return candidates[0].id if candidates and perspective != "folk" else None

    def _build_claims(self, record_id: str, event, perspective: str,
                      settlements: dict) -> tuple[list[Claim], list[str], list[str]]:
        primary = settlements.get(event.primary_location)
        subject = primary.name if primary else event.primary_location
        start_year = event.year
        end_year = event.year
        qualifiers = [f"perspective:{perspective}"]
        distortions = []
        omitted = []
        if perspective == "folk":
            start_year -= 2
            end_year += 2
            distortions.append("approximate_date")
            qualifiers.append("date_approximate")

        predicate, object_value, statement = self._event_claim(
            event, perspective, subject, settlements)
        if perspective == "official" and event.event_type in {
                "war", "rebellion", "disaster"}:
            omitted.append("ordinary_people_costs")
        if perspective == "folk":
            distortions.append("names_or_numbers_may_vary")

        claim = Claim(
            id=f"{record_id}:claim:1",
            subject=subject,
            predicate=predicate,
            object=object_value,
            statement_cn=statement,
            time_range=(start_year, end_year),
            qualifiers=qualifiers,
        )
        return [claim], distortions, omitted

    def _event_claim(self, event, perspective: str, subject: str,
                     settlements: dict) -> tuple[str, str, str]:
        details = event.details
        if event.event_type == "war":
            attacker = details.get("attacker", subject)
            defender = details.get("defender", "另一座聚落")
            outcome = details.get("outcome", details.get("outcome_type", "stalemate"))
            if perspective == "folk":
                return (
                    "war_result", "contested",
                    f"当地歌谣声称，{attacker}与{defender}交战后双方都付出了代价，"
                    "但没有一致说法能够说明谁取得了胜利。",
                )
            result_text = {
                "attacker_victory": f"{attacker}迫使{defender}的守军退却",
                "defender_victory": f"{defender}击退了{attacker}的进攻",
                "stalemate": f"{attacker}与{defender}交战后均未取得决定性胜利",
            }.get(outcome, f"{attacker}与{defender}发生了一场结果不明的战斗")
            return "war_result", outcome, f"这份记录声称，{result_text}。"

        if event.event_type == "rebellion":
            outcome = details.get("outcome_type", "uncertain")
            if perspective == "folk":
                return (
                    "rebellion_result", "contested",
                    f"当地口述称，{subject}曾发生反抗统治者的冲突，"
                    "但参与者对结局的说法并不一致。",
                )
            result_text = {
                "suppressed": "反抗被镇压",
                "partial_success": "反抗者迫使统治者作出让步",
                "ruler_overthrown": "旧统治者被推翻",
            }.get(outcome, "冲突的结局没有写清")
            return (
                "rebellion_result", outcome,
                f"这份记录声称，{subject}的叛乱中{result_text}。",
            )

        if event.event_type == "literary_work":
            title = details.get("work_title", event.title)
            author = details.get("author_name", "署名者")
            return (
                "authored_work", title,
                f"文稿署名声称，{author}创作了《{title}》。",
            )
        if event.event_type == "literary_spread":
            title = details.get("work_title", "这部作品")
            return (
                "work_circulated", title,
                f"抄写记声称，《{title}》曾在此地被重新抄录和装订。",
            )
        if event.event_type == "theoretical_work":
            title = details.get("work_title", event.title)
            author = details.get("author_name", "署名者")
            return (
                "authored_treatise", title,
                f"论著署名声称，{author}编写了《{title}》。",
            )
        if event.event_type == "discovery":
            discovery = details.get("discovery_name", event.title)
            return (
                "reported_discovery", discovery,
                f"试验记录声称，{subject}的工匠曾反复试制{discovery}。",
            )
        if event.event_type == "disaster":
            disaster = details.get("disaster_type", details.get("outcome_type", "灾害"))
            prefix = "当地口述称" if perspective == "folk" else "这份记录声称"
            return (
                "suffered_disaster", disaster,
                f"{prefix}，{subject}曾遭遇{disaster}，损失数字仍有缺漏。",
            )
        if event.event_type == "construction":
            building = details.get("building_type", "公共建筑")
            return (
                "built", building,
                f"工程记录声称，{subject}曾组织修建{building}。",
            )
        if event.event_type == "trade":
            partners = [
                settlements[pid].name for pid in event.participants
                if pid in settlements and pid != event.primary_location
            ]
            partner = partners[0] if partners else "另一处聚落"
            return (
                "opened_trade_route", partner,
                f"账簿声称，{subject}曾与{partner}保持定期货物往来。",
            )

        prefix = {
            "folk": "当地口述称",
            "merchant": "这份账目声称",
            "eyewitness": "书写者声称自己见到",
        }.get(perspective, "这份记录声称")
        return (
            f"reported_{event.event_type}", event.title,
            f"{prefix}，{event.title}曾经发生。",
        )
