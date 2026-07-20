"""
压力指标计算 + 年度经济 tick。
每年从世界状态计算一组 [0, 1] 压力指标，驱动事件规则评估。
"""

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.world import World
    from simulation.settlement import Settlement


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---- 压力计算 ----

def compute_famine_pressure(settlement: "Settlement", world: "World") -> float:
    """
    粮食库存相对消费需求的压力。
    0 = 粮食充足，1 = 严重饥荒。
    """
    annual_need = settlement.population * FOOD_CONSUMPTION_PER_CAPITA
    months_of_food = settlement.food_stock / max(annual_need, 1.0) * 12.0
    stock_pressure = clamp(1.0 - months_of_food / 12.0)
    # 实际缺粮比库存不足更严重；一年储备对应零库存压力。
    return clamp(0.70 * settlement.food_shortage + 0.30 * stock_pressure)


def compute_unrest_pressure(settlement: "Settlement", world: "World") -> float:
    """
    社会动荡压力，综合饥荒、合法性、稳定度。
    """
    famine = compute_famine_pressure(settlement, world)
    leg_inv = 1.0 - settlement.legitimacy
    stab_inv = 1.0 - settlement.stability
    return clamp(0.4 * famine + 0.3 * leg_inv + 0.3 * stab_inv)


def compute_expansion_pressure(settlement: "Settlement", world: "World") -> float:
    """
    扩张欲望：人口充裕 + 粮食充足 + 财政宽裕。
    """
    pop_factor = clamp(settlement.population / 1500.0)
    food_factor = clamp(settlement.food_stock / 1000.0)
    treasury_factor = clamp(settlement.treasury / 500.0)
    return clamp(0.4 * pop_factor + 0.3 * food_factor + 0.3 * treasury_factor)


def compute_succession_pressure(settlement: "Settlement", world: "World") -> float:
    """
    继承压力：统治者年龄、继承人状态、合法性与稳定性共同决定。
    """
    leg_inv = 1.0 - settlement.legitimacy
    stab_inv = 1.0 - settlement.stability
    ruler = world.get_person(settlement.ruler_id) if settlement.ruler_id else None
    if ruler is None or not ruler.alive:
        age_pressure = 1.0
        heir_pressure = 1.0
    else:
        age_pressure = clamp((ruler.age_at(world.current_year) - 50) / 35.0)
        has_heir = any(
            person.alive and "heir" in person.roles
            and person.settlement_id == ruler.settlement_id
            for person in world.persons.values()
        )
        heir_pressure = 0.0 if has_heir else 1.0
    return clamp(
        0.30 * leg_inv + 0.20 * stab_inv
        + 0.35 * age_pressure + 0.15 * heir_pressure)


def compute_trade_pressure(settlement: "Settlement", world: "World") -> float:
    """
    贸易需求：食物或财政不足时更需要贸易。
    """
    famine = compute_famine_pressure(settlement, world)
    treasury_need = clamp(1.0 - settlement.treasury / 400.0)
    return clamp(0.5 * famine + 0.5 * treasury_need)


def compute_disaster_risk(settlement: "Settlement", world: "World") -> float:
    """
    灾害风险：由 biome 和基础设施决定。
    """
    biome_risk = {
        "river_valley": 0.35,  # 洪水风险
        "forest": 0.25,
        "grassland": 0.20,
        "plains": 0.20,
        "scrubland": 0.25,
        "highland": 0.20,
        "desert": 0.15,        # 干旱是持续型，不是突发事件
        "tundra": 0.10,
        "mountain": 0.30,      # 地震风险
    }
    base = biome_risk.get(settlement.biome, 0.20)
    # 人口越多，受灾影响越大
    pop_factor = clamp(settlement.population / 2000.0, 0.0, 0.3)
    return clamp(base + pop_factor)


def compute_invasion_risk(settlement: "Settlement", world: "World") -> float:
    """
    被入侵风险：邻国敌意 + 军力差距（Phase 2 简化版）。
    """
    hostility_total = 0.0
    count = 0
    for rel in settlement.relationships.values():
        hostility_total += rel.hostility
        count += 1
    if count == 0:
        return 0.1
    avg_hostility = hostility_total / count

    # 稳定度低的聚落更容易被当成目标
    stab_inv = 1.0 - settlement.stability
    return clamp(0.5 * avg_hostility + 0.5 * stab_inv)


def compute_all_pressures(world: "World") -> dict[str, dict[str, float]]:
    """
    计算所有存活聚落的所有压力指标。
    返回 {settlement_id: {pressure_name: value}}。
    """
    pressures = {}
    for stl in world.settlements.values():
        if not stl.alive:
            continue
        pressures[stl.id] = {
            "famine_pressure": compute_famine_pressure(stl, world),
            "unrest_pressure": compute_unrest_pressure(stl, world),
            "expansion_pressure": compute_expansion_pressure(stl, world),
            "succession_pressure": compute_succession_pressure(stl, world),
            "trade_pressure": compute_trade_pressure(stl, world),
            "disaster_risk": compute_disaster_risk(stl, world),
            "invasion_risk": compute_invasion_risk(stl, world),
        }
    return pressures


# ---- 经济 tick ----

# 每 100 人口每年基础食物产量。数值与每人每年 10 单位消费一致。
FOOD_PRODUCTION_BASE: dict[str, float] = {
    "river_valley": 1200.0,
    "grassland": 1050.0,
    "forest": 950.0,
    "plains": 900.0,
    "scrubland": 760.0,
    "highland": 720.0,
    "desert": 620.0,
    "tundra": 560.0,
    "mountain": 680.0,
}

FOOD_CONSUMPTION_PER_CAPITA = 10.0   # 每人每年消耗
TAX_RATE_BASE = 0.15                  # 基础税率
MAINTENANCE_COST_PER_CAPITA = 0.5     # 每人每年公共支出


def tick_economy(settlement: "Settlement", world: "World", rng: random.Random) -> None:
    """
    年度经济更新：食物生产、消费、税收、维护。
    """
    if not settlement.alive:
        return

    pop = max(settlement.population, 1)

    # 1. 食物生产（受 biome 和随机气候波动影响）
    base_per_100 = FOOD_PRODUCTION_BASE.get(settlement.biome, 70.0)
    climate_variation = rng.uniform(-0.15, 0.15)  # ±15% 年度波动
    technology_multiplier = 1.0 + min(
        settlement.technology_level, 5.0) * 0.04
    production = (base_per_100 * (pop / 100.0)
                  * (1.0 + climate_variation) * technology_multiplier)
    settlement.food_surplus = production - pop * FOOD_CONSUMPTION_PER_CAPITA

    # 2. 食物消费与实际短缺
    consumption = pop * FOOD_CONSUMPTION_PER_CAPITA
    available = settlement.food_stock + production
    consumed = min(available, consumption)
    shortage = max(0.0, consumption - consumed)
    settlement.food_shortage = clamp(shortage / max(consumption, 1.0))
    settlement.food_stock = max(0.0, available - consumed)
    # 最多储存约三年口粮，防止长期正反馈使库存无限增长。
    settlement.food_stock = min(settlement.food_stock, consumption * 3.0)

    # 3. 税收收入
    tax_income = production * TAX_RATE_BASE
    settlement.treasury += tax_income

    # 4. 维护成本
    maintenance = pop * MAINTENANCE_COST_PER_CAPITA
    settlement.treasury -= maintenance
    settlement.treasury = max(0.0, settlement.treasury)

    # 5. 缺粮会造成人口损失和政治压力；无短缺时缓慢恢复。
    if settlement.food_shortage > 0:
        loss_rate = 0.02 + 0.10 * settlement.food_shortage
        settlement.population = max(10, int(settlement.population * (1.0 - loss_rate)))
        settlement.stability = clamp(
            settlement.stability - 0.08 * settlement.food_shortage)
        settlement.legitimacy = clamp(
            settlement.legitimacy - 0.03 * settlement.food_shortage)
    else:
        cultural_recovery = min(settlement.cultural_influence, 5.0) * 0.002
        settlement.stability = clamp(
            settlement.stability + rng.uniform(0.0, 0.02)
            + cultural_recovery)
        settlement.legitimacy = clamp(settlement.legitimacy + rng.uniform(0.0, 0.01))

    # 6. 关系自然衰减
    for rel in settlement.relationships.values():
        rel.hostility = clamp(rel.hostility - 0.01)  # 敌意缓慢消退
        rel.trust = clamp(rel.trust + 0.005)          # 信任微小增长


def tick_climate(world: "World", year: int, rng: random.Random) -> None:
    """
    年度气候波动 —— 存储到 World 的缓存中供事件规则使用。
    Phase 2: 目前经济 tick 中已经有随机波动，此处预留扩展点。
    """
    pass  # Phase 2 不需要额外处理，已在 tick_economy 中覆盖
