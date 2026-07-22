"""
结构化效果（Effect）系统。
每个 Effect 是一种可验证、可回滚的状态变更。
所有 Effect 都是平铺 dataclass，不用继承。
"""

import copy
import random
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from simulation.world import World


# ---- Effect 结果 ----

@dataclass
class EffectResult:
    """Effect 应用后的结果。"""
    effect_id: str = ""
    success: bool = True
    message: str = ""
    snapshot_before: dict | None = None  # 回滚用


# ---- Effect 类型 ----

@dataclass
class ModifyPopulation:
    """变更聚落人口。"""
    effect_type: ClassVar[str] = "modify_population"
    settlement_id: str
    delta: int = 0           # 绝对值变更
    percent: float = 0.0     # 比例变更 (0.1 = +10%)
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        if stl is None:
            return False
        return stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.population
        peak_before = stl.peak_population
        change = self.delta + int(stl.population * self.percent)
        stl.population = max(10, stl.population + change)
        if stl.population > stl.peak_population:
            stl.peak_population = stl.population
        return EffectResult(
            success=True,
            snapshot_before={"population": before, "peak_population": peak_before},
            message=f"{self.settlement_id}: pop {before} → {stl.population}"
        )


@dataclass
class ModifyFoodStock:
    """变更粮食库存。"""
    effect_type: ClassVar[str] = "modify_food_stock"
    settlement_id: str
    delta: float = 0.0
    percent: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        return world.settlements.get(self.settlement_id) is not None

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.food_stock
        change = self.delta + stl.food_stock * self.percent
        stl.food_stock = max(0.0, stl.food_stock + change)
        return EffectResult(
            success=True,
            snapshot_before={"food_stock": before},
            message=f"{self.settlement_id}: food {before:.0f} → {stl.food_stock:.0f}"
        )


@dataclass
class ModifyTreasury:
    """变更公共财政。"""
    effect_type: ClassVar[str] = "modify_treasury"
    settlement_id: str
    delta: float = 0.0
    percent: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        return world.settlements.get(self.settlement_id) is not None

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.treasury
        change = self.delta + stl.treasury * self.percent
        stl.treasury = max(0.0, stl.treasury + change)
        return EffectResult(
            success=True,
            snapshot_before={"treasury": before},
            message=f"{self.settlement_id}: treasury {before:.0f} → {stl.treasury:.0f}"
        )


@dataclass
class ModifyStability:
    """变更社会秩序 [0, 1]。"""
    effect_type: ClassVar[str] = "modify_stability"
    settlement_id: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.stability
        stl.stability = max(0.0, min(1.0, stl.stability + self.delta))
        return EffectResult(
            success=True,
            snapshot_before={"stability": before},
            message=f"{self.settlement_id}: stability {before:.2f} → {stl.stability:.2f}"
        )


@dataclass
class ModifyLegitimacy:
    """变更统治合法性 [0, 1]。"""
    effect_type: ClassVar[str] = "modify_legitimacy"
    settlement_id: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.legitimacy
        stl.legitimacy = max(0.0, min(1.0, stl.legitimacy + self.delta))
        return EffectResult(
            success=True,
            snapshot_before={"legitimacy": before},
            message=f"{self.settlement_id}: legitimacy {before:.2f} → {stl.legitimacy:.2f}"
        )


@dataclass
class ModifyCulturalInfluence:
    effect_type: ClassVar[str] = "modify_cultural_influence"
    settlement_id: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.cultural_influence
        stl.cultural_influence = max(
            0.0, min(10.0, before + self.delta))
        return EffectResult(
            success=True,
            snapshot_before={"cultural_influence": before},
            message=(f"{self.settlement_id}: culture {before:.2f} → "
                     f"{stl.cultural_influence:.2f}"),
        )


@dataclass
class ModifyTheoreticalKnowledge:
    effect_type: ClassVar[str] = "modify_theoretical_knowledge"
    settlement_id: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.theoretical_knowledge
        stl.theoretical_knowledge = max(
            0.0, min(10.0, before + self.delta))
        return EffectResult(
            success=True,
            snapshot_before={"theoretical_knowledge": before},
            message=(f"{self.settlement_id}: theory {before:.2f} → "
                     f"{stl.theoretical_knowledge:.2f}"),
        )


@dataclass
class ModifyTechnologyLevel:
    effect_type: ClassVar[str] = "modify_technology_level"
    settlement_id: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.technology_level
        stl.technology_level = max(
            0.0, min(10.0, before + self.delta))
        return EffectResult(
            success=True,
            snapshot_before={"technology_level": before},
            message=(f"{self.settlement_id}: technology {before:.2f} → "
                     f"{stl.technology_level:.2f}"),
        )


@dataclass
class ModifyRelationship:
    """变更两个聚落之间的关系。"""
    effect_type: ClassVar[str] = "modify_relationship"
    settlement_a: str
    settlement_b: str
    trust_delta: float = 0.0
    hostility_delta: float = 0.0
    trade_volume_delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        a = world.settlements.get(self.settlement_a)
        b = world.settlements.get(self.settlement_b)
        return a is not None and b is not None

    def apply(self, world: "World") -> EffectResult:
        from simulation.settlement import RelationshipData
        a = world.settlements[self.settlement_a]
        b = world.settlements[self.settlement_b]

        a_had_relationship = self.settlement_b in a.relationships
        b_had_relationship = self.settlement_a in b.relationships

        # 确保双边关系存在
        if not a_had_relationship:
            a.relationships[self.settlement_b] = RelationshipData(
                partner_id=self.settlement_b)
        rel_a = a.relationships[self.settlement_b]

        if not b_had_relationship:
            b.relationships[self.settlement_a] = RelationshipData(
                partner_id=self.settlement_a)
        rel_b = b.relationships[self.settlement_a]

        snapshot = {
            "a_had_relationship": a_had_relationship,
            "b_had_relationship": b_had_relationship,
            "a_trust": rel_a.trust, "a_hostility": rel_a.hostility,
            "a_trade_volume": rel_a.trade_volume,
            "a_last_interaction_year": rel_a.last_interaction_year,
            "b_trust": rel_b.trust, "b_hostility": rel_b.hostility,
            "b_trade_volume": rel_b.trade_volume,
            "b_last_interaction_year": rel_b.last_interaction_year,
        }

        rel_a.trust = max(0.0, min(1.0, rel_a.trust + self.trust_delta))
        rel_a.hostility = max(0.0, min(1.0, rel_a.hostility + self.hostility_delta))
        rel_a.trade_volume = max(0.0, rel_a.trade_volume + self.trade_volume_delta)
        rel_a.last_interaction_year = world.current_year

        rel_b.trust = max(0.0, min(1.0, rel_b.trust + self.trust_delta))
        rel_b.hostility = max(0.0, min(1.0, rel_b.hostility + self.hostility_delta))
        rel_b.trade_volume = max(0.0, rel_b.trade_volume + self.trade_volume_delta)
        rel_b.last_interaction_year = world.current_year

        return EffectResult(
            success=True, snapshot_before=snapshot,
            message=f"Relationship {self.settlement_a}<->{self.settlement_b} updated"
        )


@dataclass
class StrengthenExchangeNetwork:
    """Accumulate a reversible bilateral trade, scholarly, or cultural tie."""
    effect_type: ClassVar[str] = "strengthen_exchange_network"
    settlement_a: str
    settlement_b: str
    channel: str
    amount: float = 0.0
    event_id: str = ""
    topic_key: str = ""

    def validate(self, world: "World") -> bool:
        a = world.settlements.get(self.settlement_a)
        b = world.settlements.get(self.settlement_b)
        return (
            a is not None and a.alive
            and b is not None and b.alive
            and a.id != b.id
            and self.channel in {"trade", "scholarly", "cultural"}
            and self.amount > 0
        )

    def apply(self, world: "World") -> EffectResult:
        from simulation.settlement import RelationshipData
        a = world.settlements[self.settlement_a]
        b = world.settlements[self.settlement_b]
        a_had_relationship = b.id in a.relationships
        b_had_relationship = a.id in b.relationships
        if not a_had_relationship:
            a.relationships[b.id] = RelationshipData(partner_id=b.id)
        if not b_had_relationship:
            b.relationships[a.id] = RelationshipData(partner_id=a.id)
        rel_a = a.relationships[b.id]
        rel_b = b.relationships[a.id]
        snapshot = {
            "a_had_relationship": a_had_relationship,
            "b_had_relationship": b_had_relationship,
            "a_counts": copy.deepcopy(rel_a.exchange_counts),
            "a_strengths": copy.deepcopy(rel_a.exchange_strengths),
            "a_last_years": copy.deepcopy(rel_a.exchange_last_years),
            "a_topics": copy.deepcopy(rel_a.exchange_topics),
            "b_counts": copy.deepcopy(rel_b.exchange_counts),
            "b_strengths": copy.deepcopy(rel_b.exchange_strengths),
            "b_last_years": copy.deepcopy(rel_b.exchange_last_years),
            "b_topics": copy.deepcopy(rel_b.exchange_topics),
        }
        for relationship in (rel_a, rel_b):
            relationship.exchange_counts[self.channel] = (
                relationship.exchange_counts.get(self.channel, 0) + 1)
            relationship.exchange_strengths[self.channel] = round(min(
                10.0,
                relationship.exchange_strengths.get(self.channel, 0.0)
                + self.amount,
            ), 3)
            relationship.exchange_last_years[self.channel] = world.current_year
            if self.topic_key:
                topics = relationship.exchange_topics.setdefault(
                    self.channel, [])
                if self.topic_key not in topics:
                    topics.append(self.topic_key)
                    del topics[:-12]
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=(f"{self.settlement_a}<->{self.settlement_b}: "
                     f"{self.channel} network +{self.amount:.2f}"),
        )


@dataclass
class TransferControl:
    """转让聚落控制权（Phase 3 将用 faction_id）。"""
    effect_type: ClassVar[str] = "transfer_control"
    settlement_id: str
    old_controller_id: str | None = None
    new_controller_id: str | None = None
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        if stl is None or not stl.alive:
            return False
        return True

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.ruler_name
        # Phase 2: 控制权变化记录在案，实际统治者变更有单独的 ChangeRuler 处理
        if self.new_controller_id:
            target = world.settlements.get(self.new_controller_id)
            if target:
                stl.ruler_name = target.ruler_name
        return EffectResult(
            success=True,
            snapshot_before={"ruler_name": before},
            message=f"{self.settlement_id}: control transferred"
        )


@dataclass
class ChangeRuler:
    """变更聚落统治者。"""
    effect_type: ClassVar[str] = "change_ruler"
    settlement_id: str
    old_ruler_name: str
    new_ruler_name: str
    change_type: str = "death"  # death / abdication / deposition / conquest
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        before = stl.ruler_name
        stl.ruler_name = self.new_ruler_name
        return EffectResult(
            success=True,
            snapshot_before={"ruler_name": before},
            message=f"{self.settlement_id}: ruler {before} → {self.new_ruler_name} ({self.change_type})"
        )


@dataclass
class DamageBuilding:
    """损坏或摧毁聚落中的建筑物/设施。"""
    effect_type: ClassVar[str] = "damage_building"
    settlement_id: str
    building_type: str      # fortification / temple / market / library / aqueduct / palace
    damage_fraction: float = 0.0  # 0=无损, 1=完全摧毁
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        existed = self.building_type in stl.infrastructure
        before = stl.infrastructure.get(self.building_type, 0.0)
        storage_snapshot = world._snapshot_storage(self.settlement_id)
        stl.infrastructure[self.building_type] = max(
            0.0, before * (1.0 - max(0.0, min(1.0, self.damage_fraction))))
        world._storage_mgr.damage_building(
            stl, self.building_type, self.damage_fraction,
            world.current_year, world.evidence)
        return EffectResult(
            success=True,
            snapshot_before={
                "building_type": self.building_type,
                "value": before,
                "existed": existed,
                "storage": storage_snapshot,
            },
            message=f"{self.settlement_id}: {self.building_type} damaged {self.damage_fraction:.0%}"
        )


@dataclass
class ModifyInfrastructure:
    """增加或降低一种基础设施的等级。"""
    effect_type: ClassVar[str] = "modify_infrastructure"
    settlement_id: str
    building_type: str
    delta: float = 0.0
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        existed = self.building_type in stl.infrastructure
        before = stl.infrastructure.get(self.building_type, 0.0)
        stl.infrastructure[self.building_type] = max(0.0, before + self.delta)
        return EffectResult(
            success=True,
            snapshot_before={
                "building_type": self.building_type,
                "value": before,
                "existed": existed,
            },
            message=(f"{self.settlement_id}: {self.building_type} "
                     f"{before:.1f} → {stl.infrastructure[self.building_type]:.1f}"),
        )


@dataclass
class TransferEvidence:
    """Move one portable carrier between settlements with a reversible trail."""
    effect_type: ClassVar[str] = "transfer_evidence"
    evidence_id: str
    target_settlement_id: str
    target_site_type: str = "private_collection"
    transfer_type: str = "trade"
    event_id: str = ""
    legitimacy: str = "legal"
    new_owner_type: str | None = "settlement"
    new_owner_id: str | None = None
    resolved_claimant_id: str | None = None
    reason: str = ""

    def validate(self, world: "World") -> bool:
        evidence = world.evidence.get(self.evidence_id)
        target = world.settlements.get(self.target_settlement_id)
        if evidence is None or target is None or not target.alive:
            return False
        if evidence.location_id == target.id:
            return False
        if evidence.state in {"buried", "destroyed"}:
            return False
        if evidence.evidence_type not in {"artifact", "document"}:
            return False
        from simulation.storage import SITE_PROFILES
        return self.target_site_type in SITE_PROFILES

    def apply(self, world: "World") -> EffectResult:
        evidence = world.evidence[self.evidence_id]
        target = world.settlements[self.target_settlement_id]
        site_id = world._storage_mgr._site_id(
            target.id, self.target_site_type)
        site_existed = site_id in world.storage_sites
        snapshot = {
            "location_id": evidence.location_id,
            "container_id": evidence.container_id,
            "holder_type": evidence.holder_type,
            "holder_id": evidence.holder_id,
            "storage_position": evidence.storage_position,
            "accessibility": evidence.accessibility,
            "location_history": copy.deepcopy(evidence.location_history),
            "owner_type": evidence.owner_type,
            "owner_id": evidence.owner_id,
            "claimant_ids": list(evidence.claimant_ids),
            "physical_features": copy.deepcopy(evidence.physical_features),
            "target_site_id": site_id,
            "target_site_existed": site_existed,
        }
        site = world._storage_mgr.get_or_create_site(
            target, self.target_site_type, world.current_year)
        old_owner = evidence.owner_id
        if self.new_owner_type is not None:
            next_owner = self.new_owner_id or target.id
            if (old_owner and old_owner != next_owner
                    and self.legitimacy in {"contested", "illegal"}
                    and old_owner not in evidence.claimant_ids):
                evidence.claimant_ids.append(old_owner)
            evidence.owner_type = self.new_owner_type
            evidence.owner_id = next_owner
        if (self.resolved_claimant_id
                and self.resolved_claimant_id in evidence.claimant_ids):
            evidence.claimant_ids.remove(self.resolved_claimant_id)
        world._storage_mgr.move_evidence(
            evidence,
            site,
            world.current_year,
            self.reason or self.transfer_type,
            event_id=self.event_id or None,
            transfer_type=self.transfer_type,
            legitimacy=self.legitimacy,
        )
        clue = {
            "trade": "foreign_storage_label",
            "war_spoils": "removed_owner_mark",
            "evacuation": "emergency_wrapping",
            "theft": "removed_owner_mark",
            "smuggling": "concealed_transport_wrap",
            "resale": "mismatched_inventory_mark",
            "recovery": "return_inspection_seal",
        }.get(self.transfer_type)
        if clue:
            tag = f"provenance:{clue}"
            tags = evidence.physical_features.setdefault("tags", [])
            if tag not in tags:
                tags.append(tag)
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=(f"{evidence.id}: {snapshot['location_id']} -> "
                     f"{target.id} ({self.transfer_type})"),
        )


@dataclass
class MovePerson:
    """Move a historical person while preserving home affiliation."""
    effect_type: ClassVar[str] = "move_person"
    person_id: str
    target_settlement_id: str
    movement_type: str
    event_id: str = ""
    movement_year: int | None = None
    mobility_status: str = "visitor"
    travel_role: str = ""
    stay_until_year: int | None = None
    carried_evidence_ids: list[str] = field(default_factory=list)

    def validate(self, world: "World") -> bool:
        person = world.persons.get(self.person_id)
        target = world.settlements.get(self.target_settlement_id)
        if person is None or not person.alive:
            return False
        if target is None or not target.alive:
            return False
        return person.current_location_id != target.id

    def apply(self, world: "World") -> EffectResult:
        person = world.persons[self.person_id]
        source_id = person.current_location_id or person.settlement_id
        snapshot = {
            "current_location_id": source_id,
            "mobility_status": person.mobility_status,
            "travel_role": person.travel_role,
            "stay_until_year": person.stay_until_year,
            "carried_evidence_ids": list(person.carried_evidence_ids),
            "movement_history": copy.deepcopy(person.movement_history),
        }
        person.current_location_id = self.target_settlement_id
        person.mobility_status = self.mobility_status
        person.travel_role = self.travel_role
        person.stay_until_year = self.stay_until_year
        person.carried_evidence_ids = list(self.carried_evidence_ids)
        person.movement_history.append({
            "year": (world.current_year
                     if self.movement_year is None else self.movement_year),
            "event_id": self.event_id or None,
            "movement_type": self.movement_type,
            "from_location_id": source_id,
            "to_location_id": self.target_settlement_id,
            "mobility_status": self.mobility_status,
            "travel_role": self.travel_role,
            "stay_until_year": self.stay_until_year,
            "carried_evidence_ids": list(self.carried_evidence_ids),
        })
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=(f"{person.id}: {source_id} -> "
                     f"{self.target_settlement_id} ({self.movement_type})"),
        )


@dataclass
class RelocatePopulation:
    """Move aggregate survivors from a ruin to a living settlement."""
    effect_type: ClassVar[str] = "relocate_population"
    source_settlement_id: str
    target_settlement_id: str
    count: int
    reason: str = "post_disaster_displacement"

    def validate(self, world: "World") -> bool:
        source = world.settlements.get(self.source_settlement_id)
        target = world.settlements.get(self.target_settlement_id)
        return bool(
            source is not None and not source.alive
            and target is not None and target.alive
            and self.count > 0 and source.population >= self.count)

    def apply(self, world: "World") -> EffectResult:
        source = world.settlements[self.source_settlement_id]
        target = world.settlements[self.target_settlement_id]
        snapshot = {
            "source_population": source.population,
            "source_peak_population": source.peak_population,
            "target_population": target.population,
            "target_peak_population": target.peak_population,
        }
        source.population = max(0, source.population - self.count)
        target.population += self.count
        target.peak_population = max(
            target.peak_population, target.population)
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=(f"{self.count} people: {source.id} -> {target.id}"),
        )


@dataclass
class KillPerson:
    """Record a named person's event-linked death with rollback support."""
    effect_type: ClassVar[str] = "kill_person"
    person_id: str
    cause: str
    event_id: str = ""
    death_year: int | None = None

    def validate(self, world: "World") -> bool:
        person = world.persons.get(self.person_id)
        return person is not None and person.alive

    def apply(self, world: "World") -> EffectResult:
        person = world.persons[self.person_id]
        location_id = person.current_location_id or person.settlement_id
        snapshot = {
            "alive": person.alive,
            "death_year": person.death_year,
            "mobility_status": person.mobility_status,
            "travel_role": person.travel_role,
            "stay_until_year": person.stay_until_year,
            "carried_evidence_ids": list(person.carried_evidence_ids),
            "movement_history": copy.deepcopy(person.movement_history),
        }
        year = world.current_year if self.death_year is None else self.death_year
        person.alive = False
        person.death_year = year
        person.mobility_status = "dead"
        person.travel_role = "disaster_casualty"
        person.stay_until_year = None
        person.carried_evidence_ids = []
        person.movement_history.append({
            "year": year,
            "event_id": self.event_id or None,
            "movement_type": "disaster_death",
            "from_location_id": location_id,
            "to_location_id": location_id,
            "mobility_status": "dead",
            "travel_role": "disaster_casualty",
            "stay_until_year": None,
            "carried_evidence_ids": [],
            "cause": self.cause,
        })
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=f"{person.id}: died at {location_id} ({self.cause})",
        )


@dataclass
class MarkRuinSurvivor:
    """Keep a named survivor at a destroyed settlement as a visible NPC."""
    effect_type: ClassVar[str] = "mark_ruin_survivor"
    person_id: str
    settlement_id: str
    event_id: str = ""
    year: int | None = None

    def validate(self, world: "World") -> bool:
        person = world.persons.get(self.person_id)
        settlement = world.settlements.get(self.settlement_id)
        return bool(
            person is not None and person.alive
            and settlement is not None and not settlement.alive
            and person.current_location_id == settlement.id)

    def apply(self, world: "World") -> EffectResult:
        person = world.persons[self.person_id]
        snapshot = {
            "mobility_status": person.mobility_status,
            "travel_role": person.travel_role,
            "stay_until_year": person.stay_until_year,
            "carried_evidence_ids": list(person.carried_evidence_ids),
            "movement_history": copy.deepcopy(person.movement_history),
        }
        event_year = world.current_year if self.year is None else self.year
        person.mobility_status = "ruin_survivor"
        person.travel_role = "survivor"
        person.stay_until_year = None
        person.carried_evidence_ids = []
        person.movement_history.append({
            "year": event_year,
            "event_id": self.event_id or None,
            "movement_type": "remained_at_ruins",
            "from_location_id": self.settlement_id,
            "to_location_id": self.settlement_id,
            "mobility_status": "ruin_survivor",
            "travel_role": "survivor",
            "stay_until_year": None,
            "carried_evidence_ids": [],
        })
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=f"{person.id}: remained at ruins {self.settlement_id}",
        )


@dataclass
class DestroySettlement:
    """将聚落变为废墟，并保留足以事务回滚的快照。"""
    effect_type: ClassVar[str] = "destroy_settlement"
    settlement_id: str
    cause: str
    reason: str = ""

    def validate(self, world: "World") -> bool:
        stl = world.settlements.get(self.settlement_id)
        return stl is not None and stl.alive

    def apply(self, world: "World") -> EffectResult:
        stl = world.settlements[self.settlement_id]
        storage_snapshot = world._snapshot_storage(self.settlement_id)
        evidence_snapshot = {
            evidence.id: {
                "state": evidence.state,
                "current_durability": evidence.current_durability,
                "discoverability": evidence.discoverability,
            }
            for evidence in world.evidence.values()
            if evidence.location_id == self.settlement_id
        }
        snapshot = {
            "alive": stl.alive,
            "destroyed_year": stl.destroyed_year,
            "destruction_cause": stl.destruction_cause,
            "population": stl.population,
            "evidence": evidence_snapshot,
            "storage": storage_snapshot,
        }
        world._destroy_settlement(stl, world.current_year, self.cause)
        return EffectResult(
            success=True,
            snapshot_before=snapshot,
            message=f"{self.settlement_id}: destroyed by {self.cause}",
        )


# ---- EffectResolver ----

class EffectResolver:
    """管理 Effect 的应用、跟踪和回滚。"""

    def __init__(self, seed: int):
        self.rng = random.Random(seed + 9999)
        self.effect_counter: int = 0
        self.applied_effects: dict[str, EffectResult] = {}
        self.applied_effect_objects: dict[str, object] = {}

    def generate_id(self) -> str:
        self.effect_counter += 1
        return f"effect_{self.effect_counter:06d}"

    def apply_effects(self, effects: list, world: "World") -> list[str]:
        """
        事务性应用一组 Effect。
        如果任何一个 validate 失败，回滚全部已应用的 effect。
        返回成功应用的 effect_id 列表。
        """
        # 先校验整组，避免在已知无效的事务中产生任何状态变化。
        if any(not effect.validate(world) for effect in effects):
            return []

        applied_ids: list[str] = []
        try:
            for effect in effects:
                eid = self.generate_id()
                result = effect.apply(world)
                if not result.success:
                    raise RuntimeError(result.message or f"Effect {eid} failed")
                result.effect_id = eid
                self.applied_effects[eid] = result
                self.applied_effect_objects[eid] = effect
                applied_ids.append(eid)
            return applied_ids
        except Exception:
            for eid in reversed(applied_ids):
                self._rollback_one(
                    eid, self.applied_effect_objects[eid],
                    self.applied_effects[eid], world)
            return []

    def _rollback_one(self, effect_id: str, effect, result: EffectResult,
                      world: "World"):
        """根据 Effect 类型和应用前快照恢复状态。"""
        snapshot = result.snapshot_before
        if snapshot is None:
            return

        if isinstance(effect, ModifyPopulation):
            stl = world.settlements[effect.settlement_id]
            stl.population = snapshot["population"]
            stl.peak_population = snapshot["peak_population"]
        elif isinstance(effect, ModifyFoodStock):
            world.settlements[effect.settlement_id].food_stock = snapshot["food_stock"]
        elif isinstance(effect, ModifyTreasury):
            world.settlements[effect.settlement_id].treasury = snapshot["treasury"]
        elif isinstance(effect, ModifyStability):
            world.settlements[effect.settlement_id].stability = snapshot["stability"]
        elif isinstance(effect, ModifyLegitimacy):
            world.settlements[effect.settlement_id].legitimacy = snapshot["legitimacy"]
        elif isinstance(effect, ModifyCulturalInfluence):
            world.settlements[effect.settlement_id].cultural_influence = \
                snapshot["cultural_influence"]
        elif isinstance(effect, ModifyTheoreticalKnowledge):
            world.settlements[effect.settlement_id].theoretical_knowledge = \
                snapshot["theoretical_knowledge"]
        elif isinstance(effect, ModifyTechnologyLevel):
            world.settlements[effect.settlement_id].technology_level = \
                snapshot["technology_level"]
        elif isinstance(effect, ModifyRelationship):
            a = world.settlements[effect.settlement_a]
            b = world.settlements[effect.settlement_b]
            if snapshot["a_had_relationship"]:
                rel = a.relationships[effect.settlement_b]
                rel.trust = snapshot["a_trust"]
                rel.hostility = snapshot["a_hostility"]
                rel.trade_volume = snapshot["a_trade_volume"]
                rel.last_interaction_year = snapshot["a_last_interaction_year"]
            else:
                a.relationships.pop(effect.settlement_b, None)
            if snapshot["b_had_relationship"]:
                rel = b.relationships[effect.settlement_a]
                rel.trust = snapshot["b_trust"]
                rel.hostility = snapshot["b_hostility"]
                rel.trade_volume = snapshot["b_trade_volume"]
                rel.last_interaction_year = snapshot["b_last_interaction_year"]
            else:
                b.relationships.pop(effect.settlement_a, None)
        elif isinstance(effect, StrengthenExchangeNetwork):
            a = world.settlements[effect.settlement_a]
            b = world.settlements[effect.settlement_b]
            if snapshot["a_had_relationship"]:
                rel = a.relationships[effect.settlement_b]
                rel.exchange_counts = copy.deepcopy(snapshot["a_counts"])
                rel.exchange_strengths = copy.deepcopy(
                    snapshot["a_strengths"])
                rel.exchange_last_years = copy.deepcopy(
                    snapshot["a_last_years"])
                rel.exchange_topics = copy.deepcopy(snapshot["a_topics"])
            else:
                a.relationships.pop(effect.settlement_b, None)
            if snapshot["b_had_relationship"]:
                rel = b.relationships[effect.settlement_a]
                rel.exchange_counts = copy.deepcopy(snapshot["b_counts"])
                rel.exchange_strengths = copy.deepcopy(
                    snapshot["b_strengths"])
                rel.exchange_last_years = copy.deepcopy(
                    snapshot["b_last_years"])
                rel.exchange_topics = copy.deepcopy(snapshot["b_topics"])
            else:
                b.relationships.pop(effect.settlement_a, None)
        elif isinstance(effect, (TransferControl, ChangeRuler)):
            world.settlements[effect.settlement_id].ruler_name = snapshot["ruler_name"]
        elif isinstance(effect, (DamageBuilding, ModifyInfrastructure)):
            stl = world.settlements[effect.settlement_id]
            building_type = snapshot["building_type"]
            if snapshot["existed"]:
                stl.infrastructure[building_type] = snapshot["value"]
            else:
                stl.infrastructure.pop(building_type, None)
            if isinstance(effect, DamageBuilding):
                world._restore_storage_snapshot(snapshot["storage"])
        elif isinstance(effect, TransferEvidence):
            evidence = world.evidence[effect.evidence_id]
            evidence.location_id = snapshot["location_id"]
            evidence.container_id = snapshot["container_id"]
            evidence.holder_type = snapshot["holder_type"]
            evidence.holder_id = snapshot["holder_id"]
            evidence.storage_position = snapshot["storage_position"]
            evidence.accessibility = snapshot["accessibility"]
            evidence.location_history = copy.deepcopy(
                snapshot["location_history"])
            evidence.owner_type = snapshot["owner_type"]
            evidence.owner_id = snapshot["owner_id"]
            evidence.claimant_ids = list(snapshot["claimant_ids"])
            evidence.physical_features = copy.deepcopy(
                snapshot["physical_features"])
            target_site_id = snapshot["target_site_id"]
            if not snapshot["target_site_existed"]:
                occupied = any(
                    item.container_id == target_site_id
                    for item in world.evidence.values())
                if not occupied:
                    world.storage_sites.pop(target_site_id, None)
        elif isinstance(effect, MovePerson):
            person = world.persons[effect.person_id]
            person.current_location_id = snapshot["current_location_id"]
            person.mobility_status = snapshot["mobility_status"]
            person.travel_role = snapshot["travel_role"]
            person.stay_until_year = snapshot["stay_until_year"]
            person.carried_evidence_ids = list(
                snapshot["carried_evidence_ids"])
            person.movement_history = copy.deepcopy(
                snapshot["movement_history"])
        elif isinstance(effect, RelocatePopulation):
            source = world.settlements[effect.source_settlement_id]
            target = world.settlements[effect.target_settlement_id]
            source.population = snapshot["source_population"]
            source.peak_population = snapshot["source_peak_population"]
            target.population = snapshot["target_population"]
            target.peak_population = snapshot["target_peak_population"]
        elif isinstance(effect, KillPerson):
            person = world.persons[effect.person_id]
            person.alive = snapshot["alive"]
            person.death_year = snapshot["death_year"]
            person.mobility_status = snapshot["mobility_status"]
            person.travel_role = snapshot["travel_role"]
            person.stay_until_year = snapshot["stay_until_year"]
            person.carried_evidence_ids = list(
                snapshot["carried_evidence_ids"])
            person.movement_history = copy.deepcopy(
                snapshot["movement_history"])
        elif isinstance(effect, MarkRuinSurvivor):
            person = world.persons[effect.person_id]
            person.mobility_status = snapshot["mobility_status"]
            person.travel_role = snapshot["travel_role"]
            person.stay_until_year = snapshot["stay_until_year"]
            person.carried_evidence_ids = list(
                snapshot["carried_evidence_ids"])
            person.movement_history = copy.deepcopy(
                snapshot["movement_history"])
        elif isinstance(effect, DestroySettlement):
            stl = world.settlements[effect.settlement_id]
            stl.alive = snapshot["alive"]
            stl.destroyed_year = snapshot["destroyed_year"]
            stl.destruction_cause = snapshot["destruction_cause"]
            stl.population = snapshot["population"]
            for evidence_id, evidence_snapshot in snapshot["evidence"].items():
                evidence = world.evidence.get(evidence_id)
                if evidence is None:
                    continue
                evidence.state = evidence_snapshot["state"]
                evidence.current_durability = evidence_snapshot["current_durability"]
                evidence.discoverability = evidence_snapshot["discoverability"]
            world._restore_storage_snapshot(snapshot["storage"])

        self.applied_effects.pop(effect_id, None)
        self.applied_effect_objects.pop(effect_id, None)

    def reverse_effect(self, effect_id: str, world: "World") -> bool:
        """还原一个已应用的 effect。"""
        if (effect_id not in self.applied_effects or
                effect_id not in self.applied_effect_objects):
            return False
        result = self.applied_effects[effect_id]
        effect = self.applied_effect_objects[effect_id]
        self._rollback_one(effect_id, effect, result, world)
        return True


def effect_to_dict(effect) -> dict:
    """将 Effect 转成可随 HistoricalEvent 持久化的结构。"""
    data = asdict(effect)
    data["effect_type"] = effect.effect_type
    return data
