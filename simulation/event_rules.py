"""
事件规则系统：基于压力和条件的结构化事件触发。
替代旧的纯概率掷骰，引入 hard_conditions、score_factors 和 outcomes。
"""

import random
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING, Any

from simulation.effects import (
    ChangeRuler,
    DamageBuilding,
    DestroySettlement,
    ModifyCulturalInfluence,
    ModifyFoodStock,
    ModifyInfrastructure,
    ModifyLegitimacy,
    ModifyPopulation,
    ModifyRelationship,
    ModifyStability,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
    ModifyTreasury,
    TransferControl,
)
from simulation.mobility import settlement_connection_weight

if TYPE_CHECKING:
    from simulation.world import World
    from simulation.settlement import Settlement


# ---- 条件与因子 ----

@dataclass
class HardCondition:
    """二元前置条件。check 必须可调用。"""
    name: str
    check: Callable[["World", "Settlement", int], bool]
    description: str = ""


@dataclass
class ScoreFactor:
    """加权倾向因子。值域 [0, 1]，乘以权重后贡献到总分。"""
    name: str
    weight: float
    compute: Callable[["World", "Settlement", int], float]
    description: str = ""


@dataclass
class PossibleOutcome:
    """一个事件类型的具体结果分支。"""
    outcome_type: str
    effects: list = field(default_factory=list)
    title_template_cn: str = ""
    description_template_cn: str = ""
    severity: float = 0.5
    base_weight: float = 1.0


@dataclass
class EventRule:
    """一条事件规则。"""
    event_type: str
    hard_conditions: list = field(default_factory=list)
    score_factors: list = field(default_factory=list)
    possible_outcomes: list = field(default_factory=list)
    cooldown_years: int = 0
    mutual_exclusion_groups: list = field(default_factory=list)
    base_probability: float = 0.01
    max_probability: float = 0.90
    is_global: bool = False
    requires_two_settlements: bool = False
    evidence_recipes_key: str | None = None

    def evaluate(self, world: "World", settlement: "Settlement",
                 rng: random.Random, year: int) -> "EventRuleResult | None":
        """评估本规则。返回 EventRuleResult 或 None。"""
        # Step 1: Hard conditions
        for cond in self.hard_conditions:
            try:
                if not cond.check(world, settlement, year):
                    return None
            except Exception:
                return None

        # Step 2: Compute score
        trigger_factors = {}
        total_score = self.base_probability
        for factor in self.score_factors:
            try:
                value = factor.compute(world, settlement, year)
                value = max(0.0, min(1.0, value))
            except Exception:
                value = 0.0
            trigger_factors[factor.name] = value
            total_score += value * factor.weight
        total_score = max(0.0, min(self.max_probability, total_score))

        # Step 3: Roll
        if rng.random() > total_score:
            return None

        # Step 4: Resolve the other participant once for the whole event.
        target_settlement_id = self._select_partner(world, settlement, rng)
        if self.requires_two_settlements and target_settlement_id is None:
            return None

        # Step 5: Select an outcome using current state, not static weights alone.
        outcome = self._select_outcome(
            world, settlement, trigger_factors, rng, target_settlement_id)
        new_ruler_name = None
        if ("$NEW_RULER" in outcome.title_template_cn or
                "$NEW_RULER" in outcome.description_template_cn):
            from simulation.names import generate_name
            new_ruler_name = generate_name(rng.randint(0, 100000), "ruler")

        # Resolve effects
        context = {
            "partner_id": target_settlement_id,
            "new_ruler_name": new_ruler_name,
        }
        concrete_effects = self._resolve_effects(
            outcome, settlement, world, rng, context)

        return EventRuleResult(
            rule=self, settlement=settlement,
            total_score=total_score, trigger_factors=trigger_factors,
            selected_outcome=outcome, concrete_effects=concrete_effects,
            target_settlement_id=target_settlement_id,
            new_ruler_name=new_ruler_name,
        )

    def _select_partner(self, world, settlement, rng):
        if not self.requires_two_settlements:
            return None
        candidates = [
            other for other in world.settlements.values()
            if other.alive and other.id != settlement.id
        ]
        if not candidates:
            return None

        weights = []
        for other in candidates:
            if self.event_type in {"war", "trade"}:
                weights.append(settlement_connection_weight(
                    world, settlement, other, self.event_type))
            else:
                weights.append(1.0)
        return rng.choices(candidates, weights=weights, k=1)[0].id

    def _select_outcome(self, world, settlement, trigger_factors, rng,
                        target_settlement_id=None):
        if not self.possible_outcomes:
            return PossibleOutcome(outcome_type="default")

        weights = [o.base_weight for o in self.possible_outcomes]
        by_type = {o.outcome_type: i for i, o in enumerate(self.possible_outcomes)}

        if self.event_type == "economic":
            famine = trigger_factors.get("famine_pressure", 0.0)
            shortage = settlement.food_shortage
            if "boom" in by_type:
                weights[by_type["boom"]] *= max(0.10, 1.5 - famine - shortage)
            if "poor_harvest" in by_type:
                weights[by_type["poor_harvest"]] *= 0.25 + 2.0 * famine + 2.0 * shortage

        elif self.event_type == "rebellion":
            unrest = trigger_factors.get("unrest_pressure", 0.0)
            collapse = max(
                unrest, 1.0 - settlement.stability,
                1.0 - settlement.legitimacy)
            if "suppressed" in by_type:
                weights[by_type["suppressed"]] *= max(
                    0.15, 1.25 - 1.4 * collapse)
            if "partial_success" in by_type:
                weights[by_type["partial_success"]] *= 0.45 + collapse
            if "ruler_overthrown" in by_type:
                weights[by_type["ruler_overthrown"]] *= (
                    0.20 + 3.0 * collapse ** 2)

        elif self.event_type == "disaster":
            modifiers = {
                "river_valley": {"flood": 3.0, "drought": 0.5},
                "forest": {"fire": 2.5, "drought": 0.7},
                "desert": {"drought": 3.5, "flood": 0.2},
                "scrubland": {"drought": 2.5, "fire": 1.5},
                "mountain": {"earthquake": 3.0, "catastrophic_earthquake": 3.0,
                             "flood": 0.4},
                "highland": {"earthquake": 2.0, "catastrophic_earthquake": 2.0,
                             "storm": 1.5},
                "grassland": {"storm": 1.8, "drought": 1.4},
                "plains": {"storm": 1.7, "drought": 1.3},
                "tundra": {"storm": 1.5, "fire": 0.3},
            }
            for outcome_type, modifier in modifiers.get(settlement.biome, {}).items():
                if outcome_type in by_type:
                    weights[by_type[outcome_type]] *= modifier

        elif self.event_type == "war" and target_settlement_id:
            target = world.settlements[target_settlement_id]
            attacker_strength = (
                settlement.population / 1000.0 + settlement.treasury / 500.0 +
                settlement.stability)
            defender_strength = (
                target.population / 1000.0 + target.treasury / 500.0 +
                target.stability)
            ratio = attacker_strength / max(defender_strength, 0.1)
            if "attacker_victory" in by_type:
                weights[by_type["attacker_victory"]] *= max(0.25, ratio)
            if "defender_victory" in by_type:
                weights[by_type["defender_victory"]] *= max(0.25, 1.0 / ratio)
            if "stalemate" in by_type:
                weights[by_type["stalemate"]] *= 1.5 / (1.0 + abs(1.0 - ratio))

        return rng.choices(
            self.possible_outcomes,
            weights=weights,
            k=1
        )[0]

    def _resolve_effects(self, outcome, settlement, world, rng, context):
        resolved = []
        for effect in outcome.effects:
            resolved.append(resolve_placeholders(
                effect, settlement, world, rng, context))
        return resolved


@dataclass
class EventRuleResult:
    rule: EventRule
    settlement: Any
    total_score: float
    trigger_factors: dict
    selected_outcome: PossibleOutcome
    concrete_effects: list
    target_settlement_id: str | None = None
    new_ruler_name: str | None = None


# ---- 占位符解析 ----

def resolve_placeholders(effect, settlement, world, rng, context=None):
    """递归解析 effect 模板中的 $SETTLEMENT 等占位符。"""
    from dataclasses import fields

    context = context or {}

    if isinstance(effect, (int, float, bool, type(None))):
        return effect

    if isinstance(effect, str):
        if effect == "$SETTLEMENT":
            return settlement.id
        if effect == "$OLD_RULER":
            return settlement.ruler_name
        if effect == "$NEW_RULER":
            return context.get("new_ruler_name") or settlement.ruler_name
        if effect == "$PARTNER":
            return context.get("partner_id") or settlement.id
        return effect

    try:
        flds = fields(effect)
        kwargs = {}
        for f in flds:
            val = getattr(effect, f.name)
            if isinstance(val, str):
                kwargs[f.name] = resolve_placeholders(
                    val, settlement, world, rng, context)
            elif isinstance(val, list):
                kwargs[f.name] = [
                    resolve_placeholders(v, settlement, world, rng, context)
                    for v in val
                ]
            elif isinstance(val, dict):
                kwargs[f.name] = {
                    k: resolve_placeholders(v, settlement, world, rng, context)
                    for k, v in val.items()
                }
            else:
                kwargs[f.name] = val
        return type(effect)(**kwargs)
    except Exception:
        return effect


# ---- 事件规则注册表 ----

class EventRuleRegistry:
    """管理所有事件规则。"""

    def __init__(self):
        self.rules: dict[str, EventRule] = {}
        self._register_defaults()

    def get_rules_sorted(self) -> list[EventRule]:
        globals_ = [r for r in self.rules.values() if r.is_global]
        locals_ = [r for r in self.rules.values() if not r.is_global]
        return globals_ + locals_

    def _register_defaults(self):
        HC = lambda n, ck: HardCondition(n, ck)
        SF = lambda n, w, c: ScoreFactor(n, w, c)
        PO = PossibleOutcome

        # ---- 叛乱 ----
        self.rules["rebellion"] = EventRule(
            event_type="rebellion",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 100),
                HC("has_grievance", lambda w, s, y: (
                    s.stability < 0.72 or s.legitimacy < 0.68
                    or w.get_pressure(s.id, "famine_pressure") > 0.15)),
                HC("unrest_threshold", lambda w, s, y: w.get_pressure(s.id, "unrest_pressure") >= 0.17),
            ],
            score_factors=[
                SF("unrest_pressure", 0.12, lambda w, s, y: w.get_pressure(s.id, "unrest_pressure")),
                SF("famine_pressure", 0.08, lambda w, s, y: w.get_pressure(s.id, "famine_pressure")),
                SF("legitimacy_inverse", 0.06, lambda w, s, y: 1.0 - s.legitimacy),
                SF("stability_inverse", 0.06, lambda w, s, y: 1.0 - s.stability),
            ],
            possible_outcomes=[
                PO("suppressed", severity=0.40, base_weight=0.45,
                   title_template_cn="$SETTLEMENT_NAME暴动",
                   description_template_cn="一场小规模的骚动被迅速平息，但不安仍在暗处涌动。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.02, reason="rebellion_suppressed"),
                       ModifyStability("$SETTLEMENT", delta=-0.05, reason="rebellion_suppressed"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.03, reason="violent_suppression"),
                       ModifyTreasury("$SETTLEMENT", delta=-20.0, reason="suppression_cost"),
                   ]),
                PO("partial_success", severity=0.60, base_weight=0.35,
                   title_template_cn="$SETTLEMENT_NAME叛乱",
                   description_template_cn="暴动持续了数周才被镇压，城市遭受了相当的破坏。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.08, reason="rebellion"),
                       ModifyStability("$SETTLEMENT", delta=-0.14, reason="rebellion"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.12, reason="rebel_gains"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.25, reason="rebellion_damage"),
                       DamageBuilding("$SETTLEMENT", "market", 0.25, reason="street_fighting"),
                   ]),
                PO("ruler_overthrown", severity=0.85, base_weight=0.20,
                   title_template_cn="$SETTLEMENT_NAME政变",
                   description_template_cn="叛乱者攻入了领主大厅，$OLD_RULER被推翻。$NEW_RULER夺取了政权。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.10, reason="coup"),
                       ModifyStability("$SETTLEMENT", delta=-0.18, reason="coup"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.10, reason="new_regime"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.35, reason="coup"),
                       ChangeRuler("$SETTLEMENT", "$OLD_RULER", "$NEW_RULER",
                                   change_type="deposition", reason="rebellion"),
                       DamageBuilding("$SETTLEMENT", "palace", 0.40, reason="coup"),
                   ]),
            ],
            cooldown_years=5,
            mutual_exclusion_groups=["major_settlement_crisis"],
            base_probability=0.005, max_probability=0.30,
        )

        # ---- 经济事件 ----
        self.rules["economic"] = EventRule(
            event_type="economic",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 50),
            ],
            score_factors=[
                SF("famine_pressure", 0.07, lambda w, s, y: w.get_pressure(s.id, "famine_pressure")),
                SF("food_stock_low", 0.03, lambda w, s, y: 1.0 - min(s.food_stock / max(s.population * 10.0, 1.0), 1.0)),
                SF("food_stock_high", 0.03, lambda w, s, y: min(s.food_stock / max(s.population * 20.0, 1.0), 1.0)),
                SF("treasury_low", 0.03, lambda w, s, y: 1.0 - min(s.treasury / 500.0, 1.0)),
                SF("trade_pressure", 0.03, lambda w, s, y: w.get_pressure(s.id, "trade_pressure")),
                SF("expansion_pressure", 0.02, lambda w, s, y: w.get_pressure(s.id, "expansion_pressure")),
            ],
            possible_outcomes=[
                PO("boom", severity=0.20, base_weight=0.50,
                   title_template_cn="$SETTLEMENT_NAME的繁荣期",
                   description_template_cn="连续的丰收加之贸易增长，让$SETTLEMENT_NAME积累了可观的财富。",
                   effects=[
                       ModifyFoodStock("$SETTLEMENT", delta=100.0, percent=0.10, reason="economic_boom"),
                       ModifyTreasury("$SETTLEMENT", delta=60.0, reason="economic_boom"),
                       ModifyStability("$SETTLEMENT", delta=0.03, reason="prosperity"),
                   ]),
                PO("poor_harvest", severity=0.30, base_weight=0.50,
                   title_template_cn="$SETTLEMENT_NAME的歉收",
                   description_template_cn="今年的收成令人失望。粮价飞涨，普通民众的日子变得艰难。",
                   effects=[
                       ModifyFoodStock("$SETTLEMENT", percent=-0.35, reason="poor_harvest"),
                       ModifyTreasury("$SETTLEMENT", delta=-25.0, reason="poor_harvest"),
                       ModifyStability("$SETTLEMENT", delta=-0.05, reason="food_prices"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.03, reason="poor_harvest"),
                   ]),
            ],
            cooldown_years=2, base_probability=0.015, max_probability=0.22,
        )

        # ---- 灾害 ----
        self.rules["disaster"] = EventRule(
            event_type="disaster",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 50),
            ],
            score_factors=[
                SF("disaster_risk", 0.06, lambda w, s, y: w.get_pressure(s.id, "disaster_risk")),
                SF("famine_pressure", 0.03, lambda w, s, y: w.get_pressure(s.id, "famine_pressure")),
                SF("stability_inverse", 0.02, lambda w, s, y: 1.0 - s.stability),
            ],
            possible_outcomes=[
                PO("flood", severity=0.60, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME洪水",
                   description_template_cn="河水暴涨，一场大洪水袭击了$SETTLEMENT_NAME。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.05, reason="flood"),
                       ModifyFoodStock("$SETTLEMENT", percent=-0.40, reason="flood"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.12, reason="flood"),
                       ModifyStability("$SETTLEMENT", delta=-0.06, reason="flood"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.03, reason="flood_response"),
                       DamageBuilding("$SETTLEMENT", "market", 0.25, reason="flood"),
                   ]),
                PO("fire", severity=0.55, base_weight=0.20,
                   title_template_cn="$SETTLEMENT_NAME大火",
                   description_template_cn="一场毁灭性的大火吞噬了$SETTLEMENT_NAME。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.04, reason="fire"),
                       ModifyFoodStock("$SETTLEMENT", percent=-0.20, reason="fire"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.18, reason="fire"),
                       ModifyStability("$SETTLEMENT", delta=-0.08, reason="fire"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.03, reason="fire_response"),
                       DamageBuilding("$SETTLEMENT", "market", 0.55, reason="fire"),
                   ]),
                PO("drought", severity=0.50, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME旱灾",
                   description_template_cn="漫长的干旱让$SETTLEMENT_NAME周围的河流几近枯竭。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.03, reason="drought"),
                       ModifyFoodStock("$SETTLEMENT", percent=-0.60, reason="drought"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.10, reason="drought"),
                       ModifyStability("$SETTLEMENT", delta=-0.07, reason="drought"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.05, reason="drought_response"),
                   ]),
                PO("storm", severity=0.45, base_weight=0.20,
                   title_template_cn="$SETTLEMENT_NAME暴风雨",
                   description_template_cn="一场罕见的暴风雨席卷了$SETTLEMENT_NAME。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.02, reason="storm"),
                       ModifyFoodStock("$SETTLEMENT", percent=-0.15, reason="storm"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.08, reason="storm"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.02, reason="storm_response"),
                       DamageBuilding("$SETTLEMENT", "market", 0.20, reason="storm"),
                   ]),
                PO("earthquake", severity=0.80, base_weight=0.07,
                   title_template_cn="$SETTLEMENT_NAME地震",
                   description_template_cn="大地剧烈震颤。建筑大量倒塌。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.15, reason="earthquake"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.25, reason="earthquake"),
                       ModifyStability("$SETTLEMENT", delta=-0.15, reason="earthquake"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.06, reason="earthquake_response"),
                       DamageBuilding("$SETTLEMENT", "fortification", 0.50, reason="earthquake"),
                       DamageBuilding("$SETTLEMENT", "market", 0.45, reason="earthquake"),
                   ]),
                PO("catastrophic_earthquake", severity=0.95, base_weight=0.03,
                   title_template_cn="$SETTLEMENT_NAME毁于大地震",
                   description_template_cn="大地撕裂了$SETTLEMENT_NAME，幸存者最终放弃了这座城市。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.30,
                                        reason="catastrophic_earthquake"),
                       ModifyStability("$SETTLEMENT", delta=-0.30,
                                       reason="catastrophic_earthquake"),
                       DamageBuilding("$SETTLEMENT", "fortification", 0.90,
                                      reason="catastrophic_earthquake"),
                       DestroySettlement("$SETTLEMENT", cause="earthquake",
                                         reason="catastrophic_earthquake"),
                   ]),
            ],
            cooldown_years=3,
            mutual_exclusion_groups=["major_settlement_crisis"],
            base_probability=0.005, max_probability=0.12,
        )

        # ---- 建设 ----
        self.rules["construction"] = EventRule(
            event_type="construction",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("can_afford", lambda w, s, y: s.treasury >= 100),
            ],
            score_factors=[
                SF("treasury_high", 0.06, lambda w, s, y: min(s.treasury / 500.0, 1.0)),
                SF("food_stock_high", 0.04, lambda w, s, y: min(s.food_stock / max(s.population * 15.0, 1.0), 1.0)),
                SF("expansion_pressure", 0.04, lambda w, s, y: w.get_pressure(s.id, "expansion_pressure")),
                SF("invasion_risk", 0.03, lambda w, s, y: w.get_pressure(s.id, "invasion_risk")),
            ],
            possible_outcomes=[
                PO("temple", severity=0.20, base_weight=0.20,
                   title_template_cn="$SETTLEMENT_NAME建成神殿",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-100.0, reason="build_temple"),
                       ModifyInfrastructure("$SETTLEMENT", "temple", 1.0, reason="construction"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.03, reason="temple"),
                   ]),
                PO("market", severity=0.20, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME建成大市场",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-120.0, reason="build_market"),
                       ModifyInfrastructure("$SETTLEMENT", "market", 1.0, reason="construction"),
                       ModifyStability("$SETTLEMENT", delta=0.02, reason="market"),
                   ]),
                PO("fortification", severity=0.25, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME城墙加固",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-150.0, reason="fortification"),
                       ModifyInfrastructure("$SETTLEMENT", "fortification", 1.0, reason="construction"),
                       ModifyStability("$SETTLEMENT", delta=0.03, reason="fortification"),
                   ]),
                PO("library", severity=0.15, base_weight=0.10,
                   title_template_cn="$SETTLEMENT_NAME建成图书馆",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-110.0, reason="build_library"),
                       ModifyInfrastructure("$SETTLEMENT", "library", 1.0, reason="construction"),
                   ]),
                PO("aqueduct", severity=0.20, base_weight=0.10,
                   title_template_cn="$SETTLEMENT_NAME建成引水渠",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-140.0, reason="build_aqueduct"),
                       ModifyInfrastructure("$SETTLEMENT", "aqueduct", 1.0, reason="construction"),
                       ModifyFoodStock("$SETTLEMENT", delta=100.0, reason="aqueduct"),
                   ]),
                PO("palace", severity=0.20, base_weight=0.10,
                   title_template_cn="$SETTLEMENT_NAME建成领主大厅",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-160.0, reason="build_palace"),
                       ModifyInfrastructure("$SETTLEMENT", "palace", 1.0, reason="construction"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.05, reason="palace"),
                   ]),
            ],
            cooldown_years=5, base_probability=0.01, max_probability=0.18,
        )

        # ---- 贸易 ----
        self.rules["trade"] = EventRule(
            event_type="trade",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_partner", lambda w, s, y: sum(1 for o in w.settlements.values()
                    if o.alive and o.id != s.id) > 0),
            ],
            score_factors=[
                SF("trade_pressure", 0.07, lambda w, s, y: w.get_pressure(s.id, "trade_pressure")),
                SF("expansion_pressure", 0.04, lambda w, s, y: w.get_pressure(s.id, "expansion_pressure")),
                SF("trust_avg", 0.04, lambda w, s, y: _avg_trust(s)),
                SF("population_factor", 0.02, lambda w, s, y: min(s.population / 1000.0, 1.0)),
            ],
            possible_outcomes=[
                PO("trade_opened", severity=0.15,
                   title_template_cn="$SETTLEMENT_NAME与$PARTNER开通商路",
                   description_template_cn="两地之间的商路正式开通。",
                   effects=[
                       ModifyRelationship("$SETTLEMENT", "$PARTNER",
                                          trust_delta=0.08, hostility_delta=-0.03,
                                          trade_volume_delta=40.0, reason="trade"),
                       ModifyTreasury("$SETTLEMENT", delta=25.0, reason="trade"),
                       ModifyTreasury("$PARTNER", delta=15.0, reason="trade"),
                   ]),
            ],
            cooldown_years=3, base_probability=0.01, max_probability=0.18,
            requires_two_settlements=True,
        )

        # ---- 战争 ----
        self.rules["war"] = EventRule(
            event_type="war",
            hard_conditions=[
                HC("settlements_alive", lambda w, s, y: sum(1 for o in w.settlements.values()
                    if o.alive) >= 2),
            ],
            score_factors=[
                SF("expansion_pressure", 0.04, lambda w, s, y: w.get_pressure(s.id, "expansion_pressure")),
                SF("avg_hostility", 0.10, lambda w, s, y: _avg_hostility(s)),
                SF("invasion_risk", 0.06, lambda w, s, y: w.get_pressure(s.id, "invasion_risk")),
                SF("treasury_factor", 0.03, lambda w, s, y: min(s.treasury / 400.0, 1.0)),
            ],
            possible_outcomes=[
                PO("attacker_victory", severity=0.80, base_weight=0.30,
                   title_template_cn="$SETTLEMENT_NAME攻陷$TARGET_NAME",
                   description_template_cn="$SETTLEMENT_NAME的军队攻陷了$TARGET_NAME。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.08, reason="war"),
                       ModifyPopulation("$PARTNER", percent=-0.25, reason="war_defeat"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.18, reason="war"),
                       ModifyTreasury("$PARTNER", percent=-0.35, reason="sack"),
                       ModifyStability("$PARTNER", delta=-0.20, reason="war_defeat"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.08, reason="victory"),
                       ModifyLegitimacy("$PARTNER", delta=-0.12, reason="defeat"),
                       ModifyRelationship("$SETTLEMENT", "$PARTNER",
                                          trust_delta=-0.25, hostility_delta=0.35,
                                          reason="war"),
                       TransferControl("$PARTNER", new_controller_id="$SETTLEMENT",
                                       reason="conquest"),
                       DamageBuilding("$PARTNER", "fortification", 0.45, reason="siege"),
                   ]),
                PO("defender_victory", severity=0.60, base_weight=0.30,
                   title_template_cn="$TARGET_NAME击退$SETTLEMENT_NAME",
                   description_template_cn="$TARGET_NAME的守军成功击退了$SETTLEMENT_NAME的进攻。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.16, reason="war_defeat"),
                       ModifyPopulation("$PARTNER", percent=-0.07, reason="defense"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.25, reason="war"),
                       ModifyTreasury("$PARTNER", percent=-0.15, reason="defense"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.10, reason="defeat"),
                       ModifyLegitimacy("$PARTNER", delta=0.08, reason="victory"),
                       ModifyRelationship("$SETTLEMENT", "$PARTNER",
                                          trust_delta=-0.20, hostility_delta=0.30,
                                          reason="war"),
                       DamageBuilding("$PARTNER", "fortification", 0.20, reason="siege"),
                   ]),
                PO("stalemate", severity=0.65, base_weight=0.40,
                   title_template_cn="$SETTLEMENT_NAME与$TARGET_NAME之战",
                   description_template_cn="双方爆发激战，伤亡惨重，但都未能取得决定性胜利。",
                   effects=[
                       ModifyPopulation("$SETTLEMENT", percent=-0.12, reason="war"),
                       ModifyPopulation("$PARTNER", percent=-0.12, reason="war"),
                       ModifyTreasury("$SETTLEMENT", percent=-0.25, reason="war"),
                       ModifyTreasury("$PARTNER", percent=-0.25, reason="war"),
                       ModifyStability("$SETTLEMENT", delta=-0.07, reason="war"),
                       ModifyStability("$PARTNER", delta=-0.07, reason="war"),
                       ModifyLegitimacy("$SETTLEMENT", delta=-0.05, reason="stalemate"),
                       ModifyLegitimacy("$PARTNER", delta=-0.05, reason="stalemate"),
                       ModifyRelationship("$SETTLEMENT", "$PARTNER",
                                          trust_delta=-0.20, hostility_delta=0.30,
                                          reason="war"),
                   ]),
            ],
            cooldown_years=8,
            mutual_exclusion_groups=["major_war"],
            is_global=True, requires_two_settlements=True,
            base_probability=0.005, max_probability=0.20,
            evidence_recipes_key="war",
        )

        # ---- 文学创作 ----
        self.rules["literary_work"] = EventRule(
            event_type="literary_work",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 100),
                HC("has_library", lambda w, s, y:
                   s.infrastructure.get("library", 0.0) >= 0.5),
            ],
            score_factors=[
                SF("library_factor", 0.08, lambda w, s, y:
                   min(s.infrastructure.get("library", 0.0), 1.0)),
                SF("cultural_momentum", 0.04, lambda w, s, y:
                   min(s.cultural_influence / 3.0, 1.0)),
                SF("cultural_network", 0.03, lambda w, s, y:
                   _exchange_network_factor(s, "cultural")),
                SF("stability_factor", 0.03, lambda w, s, y: s.stability),
                SF("treasury_high", 0.02, lambda w, s, y:
                   min(s.treasury / 500.0, 1.0)),
            ],
            possible_outcomes=[
                # 新创作暂时只开放编年史和人物传记。史诗、剧作与
                # 组诗的正文渲染器仍保留，用于兼容既有世界和抄本。
                PO("chronicle", severity=0.22, base_weight=0.55,
                   title_template_cn="$SETTLEMENT_NAME编成新的地方编年史",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-22.0,
                                      reason="scribal_patronage"),
                       ModifyCulturalInfluence("$SETTLEMENT", delta=0.30,
                                               reason="civic_chronicle"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.02,
                                        reason="historical_memory"),
                   ]),
                PO("biography", severity=0.20, base_weight=0.45,
                   title_template_cn="$SETTLEMENT_NAME出现新的人物传记",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-18.0,
                                      reason="literary_patronage"),
                       ModifyCulturalInfluence("$SETTLEMENT", delta=0.28,
                                               reason="biographical_memory"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.01,
                                        reason="historical_memory"),
                   ]),
            ],
            cooldown_years=6, base_probability=0.008, max_probability=0.18,
        )

        # ---- 理论研究 ----
        self.rules["theoretical_work"] = EventRule(
            event_type="theoretical_work",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 100),
                HC("has_library", lambda w, s, y:
                   s.infrastructure.get("library", 0.0) >= 0.5),
                HC("can_support_scholar", lambda w, s, y: s.treasury >= 40.0),
            ],
            score_factors=[
                SF("library_factor", 0.09, lambda w, s, y:
                   min(s.infrastructure.get("library", 0.0), 1.0)),
                SF("theoretical_knowledge", 0.03, lambda w, s, y:
                   min(s.theoretical_knowledge / 3.0, 1.0)),
                SF("scholarly_network", 0.04, lambda w, s, y:
                   _exchange_network_factor(s, "scholarly")),
                SF("population_factor", 0.02, lambda w, s, y:
                   min(s.population / 1200.0, 1.0)),
                SF("treasury_high", 0.02, lambda w, s, y:
                   min(s.treasury / 500.0, 1.0)),
            ],
            possible_outcomes=[
                PO("mechanics", severity=0.23, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME完成一部力学论著",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-30.0,
                                      reason="research_support"),
                       ModifyTheoreticalKnowledge("$SETTLEMENT", delta=0.38,
                                                  reason="mechanics_treatise"),
                   ]),
                PO("agronomy", severity=0.22, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME完成一部农学论著",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-28.0,
                                      reason="research_support"),
                       ModifyTheoreticalKnowledge("$SETTLEMENT", delta=0.34,
                                                  reason="agronomy_treatise"),
                   ]),
                PO("medicine", severity=0.24, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME完成一部医理论著",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-32.0,
                                      reason="research_support"),
                       ModifyTheoreticalKnowledge("$SETTLEMENT", delta=0.40,
                                                  reason="medical_treatise"),
                   ]),
                PO("astronomy", severity=0.21, base_weight=0.25,
                   title_template_cn="$SETTLEMENT_NAME完成一部天文论著",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-30.0,
                                      reason="research_support"),
                       ModifyTheoreticalKnowledge("$SETTLEMENT", delta=0.36,
                                                  reason="astronomical_treatise"),
                   ]),
            ],
            cooldown_years=7, base_probability=0.008, max_probability=0.17,
        )

        # ---- 发现 ----
        self.rules["discovery"] = EventRule(
            event_type="discovery",
            hard_conditions=[
                HC("settlement_alive", lambda w, s, y: s.alive),
                HC("has_population", lambda w, s, y: s.population >= 100),
            ],
            score_factors=[
                SF("population_factor", 0.03, lambda w, s, y: min(s.population / 1500.0, 1.0)),
                SF("expansion_pressure", 0.02, lambda w, s, y: w.get_pressure(s.id, "expansion_pressure")),
                SF("treasury_high", 0.03, lambda w, s, y: min(s.treasury / 400.0, 1.0)),
                SF("legitimacy_factor", 0.02, lambda w, s, y: s.legitimacy),
                SF("library_factor", 0.04, lambda w, s, y:
                   min(s.infrastructure.get("library", 0.0), 1.0)),
                SF("theoretical_knowledge", 0.08, lambda w, s, y:
                   min(s.theoretical_knowledge, 1.0)),
                SF("scholarly_network", 0.04, lambda w, s, y:
                   _exchange_network_factor(s, "scholarly")),
            ],
            possible_outcomes=[
                PO("tech_discovery", severity=0.25,
                   title_template_cn="$SETTLEMENT_NAME的新发现",
                   description_template_cn="一项重要的新技术在$SETTLEMENT_NAME诞生了。",
                   effects=[
                       ModifyTreasury("$SETTLEMENT", delta=-25.0, reason="research"),
                       ModifyInfrastructure("$SETTLEMENT", "knowledge", 0.25,
                                            reason="discovery"),
                       ModifyTheoreticalKnowledge("$SETTLEMENT", delta=0.05,
                                                  reason="experimental_feedback"),
                       ModifyTechnologyLevel("$SETTLEMENT", delta=0.25,
                                             reason="applied_discovery"),
                       ModifyLegitimacy("$SETTLEMENT", delta=0.02,
                                        reason="prestige"),
                   ]),
            ],
            cooldown_years=8, base_probability=0.005, max_probability=0.10,
        )


# ---- 辅助函数 ----

def _avg_trust(settlement):
    if not settlement.relationships:
        return 0.3
    return sum(r.trust for r in settlement.relationships.values()) / len(settlement.relationships)

def _avg_hostility(settlement):
    if not settlement.relationships:
        return 0.1
    return sum(r.hostility for r in settlement.relationships.values()) / len(settlement.relationships)


def _exchange_network_factor(settlement, channel: str) -> float:
    strengths = [
        relationship.exchange_strengths.get(channel, 0.0)
        for relationship in settlement.relationships.values()
    ]
    return min(max(strengths, default=0.0) / 1.5, 1.0)
