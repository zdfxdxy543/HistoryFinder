"""
结构化效果（Effect）系统。
每个 Effect 是一种可验证、可回滚的状态变更。
所有 Effect 都是平铺 dataclass，不用继承。
"""

import random
from dataclasses import asdict, dataclass
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
