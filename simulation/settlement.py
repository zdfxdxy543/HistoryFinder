"""
聚落模块：聚落数据模型与简单生长逻辑。
Phase 1: 简化人口模型（logistic growth），无科技/军事/外交。
Phase 2: 增加持续状态字段（food_stock, treasury, stability, legitimacy, relationships）。
"""

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RelationshipData:
    """两个聚落之间的双边关系。"""
    partner_id: str
    trust: float = 0.5           # [0.0, 1.0]
    hostility: float = 0.1       # [0.0, 1.0]
    trade_volume: float = 0.0
    last_interaction_year: int = 0
    treaty_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "partner_id": self.partner_id,
            "trust": self.trust,
            "hostility": self.hostility,
            "trade_volume": self.trade_volume,
            "last_interaction_year": self.last_interaction_year,
            "treaty_ids": list(self.treaty_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelationshipData":
        return cls(
            partner_id=data["partner_id"],
            trust=data.get("trust", 0.5),
            hostility=data.get("hostility", 0.1),
            trade_volume=data.get("trade_volume", 0.0),
            last_interaction_year=data.get("last_interaction_year", 0),
            treaty_ids=data.get("treaty_ids", []),
        )


@dataclass
class Settlement:
    """一个聚落。"""
    id: str
    name: str
    grid_x: int
    grid_y: int
    founded_year: int
    destroyed_year: Optional[int] = None
    destruction_cause: Optional[str] = None
    alive: bool = True

    # 版本
    schema_version: int = 4

    # 人口
    population: int = 100
    peak_population: int = 100

    # 属性
    biome: str = "plains"
    size: str = "village"  # village / town / city

    # 经济（Phase 1 旧字段）
    food_surplus: float = 0.0
    wealth: float = 0.0

    # ruler_name is retained as a display/cache field for compatibility.
    ruler_name: str = ""
    ruler_id: Optional[str] = None

    # ---- Phase 2 新增：持续状态 ----
    food_stock: float = 500.0          # 粮食库存
    food_shortage: float = 0.0         # 当年未满足需求比例 [0.0, 1.0]
    treasury: float = 200.0            # 公共财政
    stability: float = 0.7             # [0.0, 1.0] 社会秩序
    legitimacy: float = 0.7            # [0.0, 1.0] 统治合法性
    cultural_influence: float = 0.0     # [0.0, 10.0]
    theoretical_knowledge: float = 0.0  # [0.0, 10.0]
    technology_level: float = 0.0       # [0.0, 10.0]
    relationships: dict[str, RelationshipData] = field(default_factory=dict)
    infrastructure: dict[str, float] = field(default_factory=dict)
    active_process_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "founded_year": self.founded_year,
            "destroyed_year": self.destroyed_year,
            "destruction_cause": self.destruction_cause,
            "alive": self.alive,
            "population": self.population,
            "peak_population": self.peak_population,
            "biome": self.biome,
            "size": self.size,
            "food_surplus": self.food_surplus,
            "wealth": self.wealth,
            "ruler_name": self.ruler_name,
            "ruler_id": self.ruler_id,
            "food_stock": self.food_stock,
            "food_shortage": self.food_shortage,
            "treasury": self.treasury,
            "stability": self.stability,
            "legitimacy": self.legitimacy,
            "cultural_influence": self.cultural_influence,
            "theoretical_knowledge": self.theoretical_knowledge,
            "technology_level": self.technology_level,
            "relationships": {k: v.to_dict() for k, v in self.relationships.items()},
            "infrastructure": dict(self.infrastructure),
            "active_process_ids": list(self.active_process_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Settlement":
        rels = {}
        for k, v in data.get("relationships", {}).items():
            rels[k] = RelationshipData.from_dict(v)
        return cls(
            id=data["id"],
            name=data["name"],
            grid_x=data["grid_x"],
            grid_y=data["grid_y"],
            founded_year=data["founded_year"],
            destroyed_year=data.get("destroyed_year"),
            destruction_cause=data.get("destruction_cause"),
            alive=data.get("alive", True),
            schema_version=data.get("schema_version", 1),
            population=data.get("population", 100),
            peak_population=data.get("peak_population", 100),
            biome=data.get("biome", "plains"),
            size=data.get("size", "village"),
            food_surplus=data.get("food_surplus", 0.0),
            wealth=data.get("wealth", 0.0),
            ruler_name=data.get("ruler_name", ""),
            ruler_id=data.get("ruler_id"),
            food_stock=data.get("food_stock", 500.0),
            food_shortage=data.get("food_shortage", 0.0),
            treasury=data.get("treasury", 200.0),
            stability=data.get("stability", 0.7),
            legitimacy=data.get("legitimacy", 0.7),
            cultural_influence=data.get("cultural_influence", 0.0),
            theoretical_knowledge=data.get("theoretical_knowledge", 0.0),
            technology_level=data.get("technology_level", 0.0),
            relationships=rels,
            infrastructure=dict(data.get("infrastructure", {})),
            active_process_ids=data.get("active_process_ids", []),
        )


class SettlementManager:
    """聚落管理器：创建、更新。"""

    def __init__(self, seed: int):
        from simulation.names import generate_name, generate_unique_name
        self.rng = random.Random(seed + 700)
        self.namer = generate_name
        self.unique_namer = generate_unique_name
        self.used_names: set[str] = set()
        self.counter = 0

    def _next_id(self) -> str:
        self.counter += 1
        return f"stl_{self.counter:04d}"

    def create_settlement(self, x: int, y: int, year: int,
                          biome: str, initial_pop: int = 100) -> Settlement:
        """在指定位置创建一个新聚落。"""
        seed = self.rng.randint(0, 100000)
        name = self.unique_namer(seed, self.used_names, "settlement")
        ruler = self.namer(seed + 1, "ruler")

        # 根据 biome 设置合理的初始状态
        food_stock_defaults = {
            "river_valley": 800.0, "grassland": 600.0, "forest": 500.0,
            "plains": 450.0, "scrubland": 300.0, "highland": 250.0,
            "desert": 150.0, "tundra": 100.0, "mountain": 200.0,
        }
        treasury_defaults = {
            "river_valley": 300.0, "grassland": 200.0, "forest": 150.0,
            "plains": 150.0, "scrubland": 100.0, "highland": 100.0,
            "desert": 80.0, "tundra": 50.0, "mountain": 100.0,
        }

        return Settlement(
            id=self._next_id(),
            name=name,
            grid_x=x,
            grid_y=y,
            founded_year=year,
            population=initial_pop,
            peak_population=initial_pop,
            biome=biome,
            ruler_name=ruler,
            food_stock=food_stock_defaults.get(biome, 400.0),
            treasury=treasury_defaults.get(biome, 150.0),
            stability=0.75,
            legitimacy=0.75,
        )

    def tick_population(self, settlement: Settlement, year: int,
                        carrying_capacity: float = 2000.0):
        """
        推进一年的人口变化。
        使用 logistic growth 模型。
        """
        if not settlement.alive:
            return

        pop = settlement.population
        K = carrying_capacity
        r = 0.03  # 基础增长率

        # logistic 增长 + 随机波动
        growth = r * pop * (1 - pop / K)
        noise = self.rng.uniform(-0.01, 0.01) * pop
        new_pop = int(pop + growth + noise)

        # 下限
        new_pop = max(new_pop, 10)

        settlement.population = new_pop
        if new_pop > settlement.peak_population:
            settlement.peak_population = new_pop

        # 根据人口更新规模
        if new_pop > 2000:
            settlement.size = "city"
        elif new_pop > 500:
            settlement.size = "town"
        else:
            settlement.size = "village"

        # 食物盈余
        settlement.food_surplus = K - new_pop

    def destroy_settlement(self, settlement: Settlement, year: int, cause: str):
        """摧毁一个聚落。"""
        settlement.alive = False
        settlement.destroyed_year = year
        settlement.destruction_cause = cause
        # 人口大幅下降但不一定归零（少数幸存者）
        settlement.population = max(int(settlement.population * 0.1), 0)

    def get_carrying_capacity(self, biome: str, base: float = 2000.0) -> float:
        """根据生物群系计算承载容量。"""
        modifiers = {
            "river_valley": 2.0,
            "grassland": 1.2,
            "forest": 1.0,
            "plains": 0.9,
            "scrubland": 0.5,
            "highland": 0.4,
            "desert": 0.2,
            "tundra": 0.15,
            "mountain": 0.3,
        }
        return base * modifiers.get(biome, 0.8)
