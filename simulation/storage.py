"""Physical storage sites and deterministic evidence placement."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from simulation.technology import TECHNOLOGY_ARTIFACT_SUBTYPES


SITE_PROFILES = {
    "library_collection": ("library", "藏书室", "supervised", 0.55, 0.55),
    "administrative_archive": ("palace", "公文档案室", "restricted", 0.62, 0.78),
    "temple_repository": ("temple", "神庙经库", "supervised", 0.65, 0.68),
    "merchant_archive": ("market", "商会账房", "permission", 0.82, 0.62),
    "private_collection": ("residence", "私人收藏室", "private", 0.78, 0.58),
    "workshop_store": ("workshop", "工坊库房", "permission", 0.92, 0.45),
    "storehouse": ("storehouse", "公共仓库", "supervised", 1.0, 0.48),
    "monument_site": (None, "公共纪念地", "public", 1.15, 0.25),
    "field_site": (None, "野外遗址", "public", 1.45, 0.10),
    "community_tradition": (None, "社区口述传承", "public", 1.0, 0.20),
}


SITE_POSITIONS = {
    "library_collection": "第{slot}号书架",
    "administrative_archive": "第{slot}号封存柜",
    "temple_repository": "第{slot}号经卷箱",
    "merchant_archive": "第{slot}号账册柜",
    "private_collection": "第{slot}号藏品箱",
    "workshop_store": "第{slot}号工具架",
    "storehouse": "第{slot}号储物格",
    "monument_site": "第{slot}号勘察点",
    "field_site": "第{slot}号遗址方格",
    "community_tradition": "第{slot}支讲述者谱系",
}


LIBRARY_DOCUMENTS = {
    "literary_manuscript", "literary_commentary", "traveling_literary_copy",
    "theoretical_treatise", "lecture_notes", "research_notes",
    "exploration_journal",
}
OFFICIAL_DOCUMENTS = {
    "founding_charter", "war_record", "reconstruction_account",
    "relief_inventory", "treaty_tablet", "construction_record",
    "succession_decree", "census_record", "tax_record", "birth_record",
    "trial_record", "omen_record",
}
PRIVATE_DOCUMENTS = {"rebel_manifesto", "marriage_contract"}
WORKSHOP_ARTIFACTS = {
    "crafted_item", "demonstration_model", "builders_tools", "reused_fittings",
} | set(TECHNOLOGY_ARTIFACT_SUBTYPES)
STOREHOUSE_ARTIFACTS = {
    "supply_crate_remains", "grain_storage_jar", "damaged_relics",
}


@dataclass
class StorageSite:
    """A persistent place that can hold evidence or a documentary collection."""

    id: str
    settlement_id: str
    site_type: str
    name: str
    building_type: Optional[str] = None
    owner_person_id: Optional[str] = None
    accessibility: str = "public"
    preservation_modifier: float = 1.0
    security: float = 0.5
    condition: float = 1.0
    created_year: int = 0
    destroyed_year: Optional[int] = None
    alive: bool = True
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "settlement_id": self.settlement_id,
            "site_type": self.site_type,
            "name": self.name,
            "building_type": self.building_type,
            "owner_person_id": self.owner_person_id,
            "accessibility": self.accessibility,
            "preservation_modifier": self.preservation_modifier,
            "security": self.security,
            "condition": self.condition,
            "created_year": self.created_year,
            "destroyed_year": self.destroyed_year,
            "alive": self.alive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StorageSite":
        return cls(
            id=data["id"],
            settlement_id=data["settlement_id"],
            site_type=data["site_type"],
            name=data["name"],
            building_type=data.get("building_type"),
            owner_person_id=data.get("owner_person_id"),
            accessibility=data.get("accessibility", "public"),
            preservation_modifier=float(data.get("preservation_modifier", 1.0)),
            security=float(data.get("security", 0.5)),
            condition=float(data.get("condition", 1.0)),
            created_year=int(data.get("created_year", 0)),
            destroyed_year=data.get("destroyed_year"),
            alive=bool(data.get("alive", True)),
            schema_version=int(data.get("schema_version", 1)),
        )

    @property
    def effective_preservation_modifier(self) -> float:
        """Damaged buildings lose part of their preservation advantage."""
        return self.preservation_modifier * (1.0 + (1.0 - self.condition) * 0.8)


class StorageManager:
    """Create/reuse storage sites and place evidence without consuming world RNG."""

    def __init__(self, seed: int, sites: dict[str, StorageSite]):
        self.seed = seed
        self.sites = sites

    @staticmethod
    def _site_id(settlement_id: str, site_type: str,
                 owner_person_id: Optional[str] = None) -> str:
        owner = owner_person_id or "shared"
        return f"site_{settlement_id}_{site_type}_{owner}"

    def get_or_create_site(self, settlement, site_type: str, year: int,
                           owner_person_id: Optional[str] = None) -> StorageSite:
        site_id = self._site_id(settlement.id, site_type, owner_person_id)
        existing = self.sites.get(site_id)
        if existing is not None:
            return existing
        building, label, accessibility, preservation, security = \
            SITE_PROFILES[site_type]
        if owner_person_id:
            name = f"{settlement.name}的{label}"
        else:
            name = f"{settlement.name}{label}"
        site = StorageSite(
            id=site_id,
            settlement_id=settlement.id,
            site_type=site_type,
            name=name,
            building_type=building,
            owner_person_id=owner_person_id,
            accessibility=accessibility,
            preservation_modifier=preservation,
            security=security,
            created_year=year,
        )
        self.sites[site.id] = site
        return site

    def _primary_site_type(self, evidence) -> str:
        subtype = (evidence.subtype.removesuffix("_copy")
                   if evidence.is_copy_of else evidence.subtype)
        if evidence.evidence_type == "oral":
            return "community_tradition"
        if evidence.location_type in ("near_settlement", "grid_cell"):
            return "field_site"
        if evidence.evidence_type in ("structure", "environmental"):
            return "monument_site"
        if evidence.evidence_type == "document":
            if subtype in LIBRARY_DOCUMENTS:
                return "library_collection"
            if subtype == "religious_text":
                return "temple_repository"
            if subtype == "trade_ledger":
                return "merchant_archive"
            if subtype in PRIVATE_DOCUMENTS:
                return "private_collection"
            if subtype in OFFICIAL_DOCUMENTS:
                return "administrative_archive"
            return "administrative_archive"
        if subtype in WORKSHOP_ARTIFACTS:
            return "workshop_store"
        if subtype in STOREHOUSE_ARTIFACTS:
            return "storehouse"
        return "private_collection"

    @staticmethod
    def _copy_site_type(primary_type: str) -> str:
        alternatives = {
            "library_collection": "private_collection",
            "administrative_archive": "library_collection",
            "temple_repository": "library_collection",
            "merchant_archive": "private_collection",
            "private_collection": "library_collection",
        }
        return alternatives.get(primary_type, primary_type)

    def assign_evidence(self, evidence, settlement, year: int,
                        owner_person_id: Optional[str] = None,
                        reason: str = "initial_deposit") -> StorageSite:
        site_type = self._primary_site_type(evidence)
        if evidence.is_copy_of and evidence.evidence_type == "document":
            site_type = self._copy_site_type(site_type)
        private_owner = owner_person_id if site_type == "private_collection" else None
        site = self.get_or_create_site(
            settlement, site_type, year, private_owner)
        self.move_evidence(evidence, site, year, reason)
        return site

    def move_evidence(self, evidence, site: StorageSite, year: int,
                      reason: str, *, event_id: str | None = None,
                      transfer_type: str = "storage",
                      legitimacy: str = "routine") -> None:
        previous = evidence.container_id
        if previous == site.id:
            return
        previous_site = self.sites.get(previous)
        evidence.location_history.append({
            "year": year,
            "event_id": event_id,
            "transfer_type": transfer_type,
            "from_location_id": (
                previous_site.settlement_id if previous_site else None),
            "to_location_id": site.settlement_id,
            "from_container_id": previous,
            "to_container_id": site.id,
            "from_holder_type": evidence.holder_type,
            "from_holder_id": evidence.holder_id,
            "to_holder_type": "site",
            "to_holder_id": site.id,
            "reason": reason,
            "legitimacy": legitimacy,
        })
        evidence.container_id = site.id
        evidence.holder_type = "site"
        evidence.holder_id = site.id
        evidence.location_id = site.settlement_id
        evidence.accessibility = site.accessibility
        digest = hashlib.sha256(
            f"{self.seed}|{evidence.id}|{site.id}".encode("utf-8")
        ).digest()
        slot = int.from_bytes(digest[:2], "big") % 24 + 1
        evidence.storage_position = SITE_POSITIONS[site.site_type].format(slot=slot)

    def damage_building(self, settlement, building_type: str, fraction: float,
                        year: int, evidence_dict: dict) -> None:
        fraction = max(0.0, min(1.0, fraction))
        affected = [site for site in self.sites.values()
                    if site.settlement_id == settlement.id
                    and site.alive and site.building_type == building_type]
        for site in affected:
            site.condition = max(0.0, site.condition * (1.0 - fraction))
            if site.condition > 0.05:
                continue
            site.alive = False
            site.destroyed_year = year
            fallback = self.get_or_create_site(
                settlement, "storehouse", year)
            if fallback.id == site.id or not fallback.alive:
                fallback = self.get_or_create_site(
                    settlement, "field_site", year)
            for evidence in evidence_dict.values():
                if evidence.container_id == site.id and evidence.state != "destroyed":
                    self.move_evidence(
                        evidence, fallback, year,
                        f"evacuated_after_{building_type}_damage")

    def destroy_settlement(self, settlement, year: int, cause: str,
                           evidence_dict: dict) -> None:
        previous_sites = [site for site in self.sites.values()
                          if site.settlement_id == settlement.id and site.alive]
        for site in previous_sites:
            site.alive = False
            site.condition = 0.0
            site.destroyed_year = year
        ruins = self.get_or_create_site(settlement, "field_site", year)
        ruins.name = f"{settlement.name}废墟遗址"
        ruins.alive = True
        ruins.condition = 1.0
        ruins.destroyed_year = None
        for evidence in evidence_dict.values():
            if (evidence.location_id == settlement.id
                    and evidence.state != "destroyed"):
                self.move_evidence(
                    evidence, ruins, year, f"settlement_destroyed:{cause}")
                if evidence.state == "buried":
                    evidence.accessibility = "buried"
