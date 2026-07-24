"""Persistent, mortal informants and the knowledge they actually hold."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from simulation.names import generate_unique_name
from simulation.person import Person


INFORMANT_ROLES = (
    "scholar", "scribe", "elder", "merchant", "artisan", "priest",
)


ROLE_PERSON_ROLES = {
    "scholar": "scholar",
    "scribe": "scribe",
    "elder": "elder",
    "merchant": "merchant",
    "artisan": "artisan",
    "priest": "priest",
}


ROLE_EXPERTISE = {
    "scholar": {
        "paleography": 0.70,
        "natural_philosophy": 0.72,
        "literature": 0.58,
        "administration": 0.38,
        "astronomy": 0.48,
    },
    "scribe": {
        "paleography": 0.76,
        "administration": 0.72,
        "literature": 0.42,
        "languages": 0.58,
    },
    "elder": {
        "local_history": 0.78,
        "genealogy": 0.56,
        "festival": 0.46,
    },
    "merchant": {
        "trade": 0.80,
        "administration": 0.46,
        "languages": 0.48,
        "travel": 0.52,
    },
    "artisan": {
        "craftsmanship": 0.82,
        "architecture": 0.54,
        "warfare": 0.30,
        "natural_philosophy": 0.34,
    },
    "priest": {
        "religion": 0.84,
        "local_history": 0.58,
        "paleography": 0.55,
        "languages": 0.42,
        "astronomy": 0.35,
    },
}


ROLE_INSTITUTIONS = {
    "scholar": ["library_collection"],
    "scribe": ["administrative_archive", "library_collection"],
    "elder": ["oral_tradition"],
    "merchant": ["merchant_archive"],
    "artisan": ["workshop_collection"],
    "priest": ["temple_repository", "community_tradition"],
}


DOCUMENT_ROLE_RULES = {
    "scholar": {
        "literary_manuscript", "literary_commentary",
        "traveling_literary_copy", "theoretical_treatise",
        "lecture_notes", "research_notes", "omen_record",
        "exploration_journal",
    },
    "merchant": {
        "trade_ledger", "tax_record", "relief_inventory",
        "census_record", "exploration_journal",
    },
    "artisan": {
        "construction_record", "research_notes",
        "reconstruction_account",
    },
    "priest": {
        "religious_text", "ritual_calendar", "reformed_liturgy",
        "reform_decree", "prohibition_edict", "omen_record",
    },
}


@dataclass
class Informant:
    id: str
    person_id: str
    settlement_id: str
    role: str
    expertise: dict[str, float]
    language_proficiency: dict[str, float] = field(
        default_factory=lambda: {"common": 1.0})
    known_entry_ids: list[str] = field(default_factory=list)
    institution_access: list[str] = field(default_factory=list)
    created_year: int = 0
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "person_id": self.person_id,
            "settlement_id": self.settlement_id,
            "role": self.role,
            "expertise": dict(self.expertise),
            "language_proficiency": dict(self.language_proficiency),
            "known_entry_ids": list(self.known_entry_ids),
            "institution_access": list(self.institution_access),
            "created_year": self.created_year,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Informant":
        return cls(
            id=data["id"],
            person_id=data["person_id"],
            settlement_id=data["settlement_id"],
            role=data["role"],
            expertise={
                key: float(value)
                for key, value in data.get("expertise", {}).items()
            },
            language_proficiency={
                key: float(value)
                for key, value in data.get(
                    "language_proficiency", {"common": 1.0}).items()
            },
            known_entry_ids=list(data.get("known_entry_ids", [])),
            institution_access=list(data.get("institution_access", [])),
            created_year=int(data.get("created_year", 0)),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class KnowledgeEntry:
    id: str
    holder_id: str
    entry_type: str
    source_evidence_id: str
    source_record_id: str
    source_root_id: str
    claim_ids: list[str]
    topic_keys: list[str]
    location_ids: list[str]
    learned_year: int
    transmission_depth: int = 0
    certainty: float = 0.5
    recognition_features: list[str] = field(default_factory=list)
    parent_entry_id: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "holder_id": self.holder_id,
            "entry_type": self.entry_type,
            "source_evidence_id": self.source_evidence_id,
            "source_record_id": self.source_record_id,
            "source_root_id": self.source_root_id,
            "claim_ids": list(self.claim_ids),
            "topic_keys": list(self.topic_keys),
            "location_ids": list(self.location_ids),
            "learned_year": self.learned_year,
            "transmission_depth": self.transmission_depth,
            "certainty": self.certainty,
            "recognition_features": list(self.recognition_features),
            "parent_entry_id": self.parent_entry_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        return cls(
            id=data["id"],
            holder_id=data["holder_id"],
            entry_type=data.get("entry_type", "record_excerpt"),
            source_evidence_id=data.get("source_evidence_id", ""),
            source_record_id=data.get("source_record_id", ""),
            source_root_id=data.get("source_root_id", ""),
            claim_ids=list(data.get("claim_ids", [])),
            topic_keys=list(data.get("topic_keys", [])),
            location_ids=list(data.get("location_ids", [])),
            learned_year=int(data.get("learned_year", 0)),
            transmission_depth=int(data.get("transmission_depth", 0)),
            certainty=float(data.get("certainty", 0.5)),
            recognition_features=list(data.get(
                "recognition_features", [])),
            parent_entry_id=data.get("parent_entry_id"),
            schema_version=int(data.get("schema_version", 1)),
        )


class InformantManager:
    def __init__(self, seed: int,
                 informants: dict[str, Informant] | None = None,
                 entries: dict[str, KnowledgeEntry] | None = None):
        self.seed = seed
        self.informants = informants if informants is not None else {}
        self.entries = entries if entries is not None else {}
        self.informant_counter = self._max_suffix(self.informants)
        self.person_counter = self._max_suffix(
            (item.person_id for item in self.informants.values()),
            marker="person_informant_")
        self.entry_counter = self._max_suffix(self.entries)

    @staticmethod
    def _max_suffix(values, marker: str = "") -> int:
        maximum = 0
        for value in values:
            tail = value.removeprefix(marker) if marker else value.rsplit("_", 1)[-1]
            if tail.isdigit():
                maximum = max(maximum, int(tail))
        return maximum

    def ensure_settlement_roles(
            self, world, settlement, year: int,
            active_roles: set[str] | None = None) -> None:
        if not settlement.alive:
            return
        for role in INFORMANT_ROLES:
            if ((active_roles is not None and role in active_roles)
                    or (active_roles is None
                        and self._active_for_role(
                            world, settlement.id, role))):
                continue
            previous = self._latest_for_role(settlement.id, role)
            person = self._find_unregistered_person(
                world, settlement.id, role)
            if person is None:
                person = self._create_person(world, settlement.id, role, year)
            informant = self._create_informant(
                settlement.id, role, person.id, year)
            if active_roles is not None:
                active_roles.add(role)
            if previous is not None:
                self._transfer_knowledge(previous, informant, year)

    def ensure_all_roles(self, world, year: int) -> None:
        active_by_settlement = {
            settlement_id: set() for settlement_id in world.settlements
        }
        for informant in self.informants.values():
            settlement = world.settlements.get(informant.settlement_id)
            person = world.persons.get(informant.person_id)
            if (settlement is not None and settlement.alive
                    and person is not None and person.alive
                    and person.current_location_id == settlement.id):
                active_by_settlement[settlement.id].add(informant.role)

        for settlement in sorted(
                world.settlements.values(), key=lambda item: item.id):
            self.ensure_settlement_roles(
                world, settlement, year,
                active_by_settlement[settlement.id])

    def active_informants(self, world, settlement_id: str,
                          roles: set[str] | None = None) -> list[Informant]:
        settlement = world.settlements.get(settlement_id)
        if settlement is None:
            return []
        result = []
        for informant in self.informants.values():
            if roles is not None and informant.role not in roles:
                continue
            person = world.persons.get(informant.person_id)
            if (person is not None and person.alive
                    and person.current_location_id == settlement_id
                    and (settlement.alive
                         or person.mobility_status == "ruin_survivor")):
                result.append(informant)
        return sorted(result, key=lambda item: (item.role, item.id))

    def distribute_carrier(self, world, evidence, record, year: int) -> None:
        if record is None or evidence.is_copy_of:
            return
        retained = set(evidence.retained_claim_ids)
        claims = [
            claim for claim in record.claimed_facts if claim.id in retained]
        if not claims:
            return
        roles = self._recipient_roles(evidence, record)
        recipients = self.active_informants(
            world, evidence.location_id, roles)
        for informant in recipients:
            if any(
                    self.entries[entry_id].source_evidence_id == evidence.id
                    for entry_id in informant.known_entry_ids
                    if entry_id in self.entries):
                continue
            self._create_entry(
                holder=informant,
                entry_type=("oral_account"
                            if evidence.evidence_type == "oral"
                            else "record_excerpt"),
                evidence=evidence,
                record=record,
                claims=claims,
                learned_year=max(year, informant.created_year),
            )

    def rebuild_current_knowledge(self, world, year: int) -> None:
        for evidence in sorted(
                world.evidence.values(), key=lambda item: item.id):
            if evidence.state == "destroyed":
                continue
            record = world.records.get(evidence.source_record_id)
            self.distribute_carrier(world, evidence, record, year)

    def _active_for_role(self, world, settlement_id: str,
                         role: str) -> Informant | None:
        active = [
            informant for informant in self.active_informants(
                world, settlement_id, {role})
            if informant.settlement_id == settlement_id
        ]
        return active[0] if active else None

    def _latest_for_role(self, settlement_id: str,
                         role: str) -> Informant | None:
        candidates = [
            item for item in self.informants.values()
            if item.settlement_id == settlement_id and item.role == role
        ]
        return max(candidates, key=lambda item: (
            item.created_year, item.id)) if candidates else None

    def _find_unregistered_person(self, world, settlement_id: str,
                                  role: str) -> Person | None:
        registered = {item.person_id for item in self.informants.values()}
        person_role = ROLE_PERSON_ROLES[role]
        candidates = [
            person for person in world.persons.values()
            if person.alive and person.settlement_id == settlement_id
            and person.current_location_id == settlement_id
            and person.id not in registered and person_role in person.roles
        ]
        return sorted(candidates, key=lambda item: item.id)[0] \
            if candidates else None

    def _create_person(self, world, settlement_id: str,
                       role: str, year: int) -> Person:
        self.person_counter += 1
        person_id = f"person_informant_{self.person_counter:05d}"
        key = f"{self.seed}|{settlement_id}|{role}|{year}|{person_id}"
        age_ranges = {
            "elder": (50, 68),
            "scholar": (28, 52),
            "scribe": (24, 48),
            "merchant": (25, 50),
            "artisan": (25, 52),
            "priest": (30, 60),
        }
        minimum, maximum = age_ranges[role]
        age = minimum + self._stable_int(key, "age") % (maximum - minimum + 1)
        name_seed = self._stable_int(key, "name")
        name = generate_unique_name(
            name_seed,
            {person.name for person in world.persons.values()},
            "ruler",
        )
        person = Person(
            id=person_id,
            name=name,
            birth_year=year - age,
            settlement_id=settlement_id,
            roles=[ROLE_PERSON_ROLES[role]],
        )
        world.persons[person.id] = person
        return person

    def _create_informant(self, settlement_id: str, role: str,
                          person_id: str, year: int) -> Informant:
        self.informant_counter += 1
        informant_id = f"informant_{self.informant_counter:05d}"
        expertise = {}
        for domain, base in ROLE_EXPERTISE[role].items():
            variation = (
                self._stable_int(informant_id, domain) % 17 - 8) / 100.0
            expertise[domain] = max(0.05, min(0.95, base + variation))
        informant = Informant(
            id=informant_id,
            person_id=person_id,
            settlement_id=settlement_id,
            role=role,
            expertise=expertise,
            institution_access=list(ROLE_INSTITUTIONS[role]),
            created_year=year,
        )
        self.informants[informant.id] = informant
        return informant

    def _create_entry(self, holder: Informant, entry_type: str,
                      evidence, record, claims: list,
                      learned_year: int) -> KnowledgeEntry:
        self.entry_counter += 1
        entry = KnowledgeEntry(
            id=f"knowledge_entry_{self.entry_counter:06d}",
            holder_id=holder.id,
            entry_type=entry_type,
            source_evidence_id=evidence.id,
            source_record_id=record.id,
            source_root_id=record.copy_parent_id or record.id,
            claim_ids=[claim.id for claim in claims],
            topic_keys=sorted({claim.topic_key() for claim in claims}),
            location_ids=[evidence.location_id],
            learned_year=learned_year,
            transmission_depth=0,
            certainty=self._initial_certainty(evidence, record),
            recognition_features=self._recognition_features(
                evidence, record, claims),
        )
        self.entries[entry.id] = entry
        holder.known_entry_ids.append(entry.id)
        return entry

    def _transfer_knowledge(self, previous: Informant,
                            successor: Informant, year: int) -> None:
        for entry_id in previous.known_entry_ids:
            parent = self.entries.get(entry_id)
            if parent is None or parent.certainty < 0.18:
                continue
            self.entry_counter += 1
            inherited = KnowledgeEntry(
                id=f"knowledge_entry_{self.entry_counter:06d}",
                holder_id=successor.id,
                entry_type=parent.entry_type,
                source_evidence_id=parent.source_evidence_id,
                source_record_id=parent.source_record_id,
                source_root_id=parent.source_root_id,
                claim_ids=list(parent.claim_ids),
                topic_keys=list(parent.topic_keys),
                location_ids=list(parent.location_ids),
                learned_year=year,
                transmission_depth=parent.transmission_depth + 1,
                certainty=max(0.05, parent.certainty * 0.84),
                recognition_features=list(parent.recognition_features),
                parent_entry_id=parent.id,
            )
            self.entries[inherited.id] = inherited
            successor.known_entry_ids.append(inherited.id)

    @staticmethod
    def _recipient_roles(evidence, record) -> set[str]:
        if evidence.evidence_type == "oral":
            roles = {"elder"}
            if record.carrier_subtype in {
                    "hymn", "festival_song", "revised_hymn",
                    "forbidden_hymn", "omen_story"}:
                roles.add("priest")
            if record.record_type in {"ledger", "receipt"}:
                roles.add("merchant")
            return roles
        if evidence.evidence_type != "document":
            return set()
        roles = {"scribe"}
        subtype = record.carrier_subtype
        for role, subtypes in DOCUMENT_ROLE_RULES.items():
            if subtype in subtypes:
                roles.add(role)
        return roles

    @staticmethod
    def _initial_certainty(evidence, record) -> float:
        condition = (
            evidence.current_durability / evidence.max_durability
            if evidence.max_durability > 0 else 0.0)
        perspective = {
            "scholarly": 0.78,
            "merchant": 0.72,
            "eyewitness": 0.70,
            "official": 0.66,
            "author": 0.64,
            "opposition": 0.58,
            "folk": 0.48,
            "ritual_office": 0.62,
        }.get(record.perspective, 0.55)
        return max(0.10, min(0.95, 0.45 * condition + 0.55 * perspective))

    @staticmethod
    def _recognition_features(evidence, record, claims: list) -> list[str]:
        features = [
            f"carrier:{record.carrier_subtype}",
            f"record_type:{record.record_type}",
        ]
        features.extend(f"predicate:{claim.predicate}" for claim in claims)
        for tag in evidence.physical_features.get("tags", []):
            if tag.startswith(("script:", "mark:", "form:")):
                features.append(tag)
        return list(dict.fromkeys(features))

    def _stable_int(self, *parts: str) -> int:
        payload = "|".join((str(self.seed), *parts)).encode("utf-8")
        return int(hashlib.sha256(payload).hexdigest()[:16], 16)
