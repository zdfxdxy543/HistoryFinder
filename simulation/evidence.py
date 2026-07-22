"""
证据系统：证据的创建、衰减、摧毁、埋藏。
Phase 2: 完整衰减模型——自然衰减 + 事件驱动摧毁 + 埋藏保存。
"""

import copy as copy_module
import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional
from config import MATERIAL_DURABILITY, MATERIAL_DECAY_RATE
from simulation.written_content import (
    PUBLIC_INSCRIPTION_SUBTYPES,
    build_written_content,
    build_written_copy_content,
)
from simulation.text_carriers import (
    advance_text_damage,
    initialize_text_plan,
    prepare_materialized_carrier,
)
from simulation.technology import TECHNOLOGY_BY_SUBTYPE


@dataclass
class Evidence:
    """一件历史证据。"""
    id: str
    event_id: str
    evidence_type: str
    subtype: str
    location_type: str  # "settlement" / "near_settlement" / "grid_cell"
    location_id: str
    created_year: int
    material: str
    max_durability: float
    current_durability: float
    state: str = "intact"  # intact / weathered / ruined / buried / destroyed
    source_record_id: Optional[str] = None
    source_event_ids: list[str] = field(default_factory=list)
    is_copy_of: Optional[str] = None
    discoverability: float = 0.8
    content_data: dict = field(default_factory=dict)
    narrative_bias: str = "neutral"
    physical_features: dict = field(default_factory=dict)
    retained_claim_ids: list[str] = field(default_factory=list)
    provenance_clues: dict = field(default_factory=dict)
    contamination: list[str] = field(default_factory=list)
    authenticity: str = "original"
    accessibility: str = "public"
    container_id: Optional[str] = None
    holder_type: str = "ground"  # site / person / ground
    holder_id: Optional[str] = None
    storage_position: str = ""
    location_history: list[dict] = field(default_factory=list)
    origin_location_id: str = ""
    owner_type: str = "settlement"  # settlement / person / institution / unknown
    owner_id: Optional[str] = None
    claimant_ids: list[str] = field(default_factory=list)

    # 版本
    schema_version: int = 7

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "event_id": self.event_id,
            "source_record_id": self.source_record_id,
            "source_event_ids": list(self.source_event_ids),
            "evidence_type": self.evidence_type,
            "subtype": self.subtype,
            "location_type": self.location_type,
            "location_id": self.location_id,
            "created_year": self.created_year,
            "material": self.material,
            "max_durability": self.max_durability,
            "current_durability": self.current_durability,
            "state": self.state,
            "is_copy_of": self.is_copy_of,
            "discoverability": self.discoverability,
            "content_data": dict(self.content_data),
            "narrative_bias": self.narrative_bias,
            "physical_features": dict(self.physical_features),
            "retained_claim_ids": list(self.retained_claim_ids),
            "provenance_clues": dict(self.provenance_clues),
            "contamination": list(self.contamination),
            "authenticity": self.authenticity,
            "accessibility": self.accessibility,
            "container_id": self.container_id,
            "holder_type": self.holder_type,
            "holder_id": self.holder_id,
            "storage_position": self.storage_position,
            "location_history": [dict(item) for item in self.location_history],
            "origin_location_id": self.origin_location_id,
            "owner_type": self.owner_type,
            "owner_id": self.owner_id,
            "claimant_ids": list(self.claimant_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        return cls(
            id=data["id"],
            event_id=data["event_id"],
            evidence_type=data["evidence_type"],
            subtype=data["subtype"],
            location_type=data["location_type"],
            location_id=data["location_id"],
            created_year=data["created_year"],
            material=data["material"],
            max_durability=data["max_durability"],
            current_durability=data["current_durability"],
            state=data.get("state", "intact"),
            source_record_id=data.get("source_record_id"),
            source_event_ids=list(data.get(
                "source_event_ids", [data["event_id"]])),
            is_copy_of=data.get("is_copy_of"),
            discoverability=data.get("discoverability", 0.8),
            content_data=data.get("content_data", {}),
            narrative_bias=data.get("narrative_bias", "neutral"),
            physical_features=dict(data.get("physical_features", {})),
            retained_claim_ids=list(data.get("retained_claim_ids", [])),
            provenance_clues=dict(data.get("provenance_clues", {})),
            contamination=list(data.get("contamination", [])),
            authenticity=data.get("authenticity", "original"),
            accessibility=data.get("accessibility", "public"),
            container_id=data.get("container_id"),
            holder_type=data.get("holder_type", "ground"),
            holder_id=data.get("holder_id"),
            storage_position=data.get("storage_position", ""),
            location_history=[dict(item) for item in data.get(
                "location_history", [])],
            origin_location_id=data.get(
                "origin_location_id",
                data.get("provenance_clues", {}).get(
                    "origin_location_id", data.get("location_id", ""))),
            owner_type=data.get("owner_type", "settlement"),
            owner_id=data.get("owner_id", data.get("location_id")),
            claimant_ids=list(data.get("claimant_ids", [])),
            schema_version=data.get("schema_version", 1),
        )

    def update_state(self):
        """根据耐久度更新状态。"""
        if self.state in ("buried", "destroyed"):
            return
        ratio = self.current_durability / self.max_durability if self.max_durability > 0 else 0
        if ratio <= 0:
            self.state = "destroyed"
        elif ratio < 0.3:
            self.state = "ruined"
        elif ratio < 0.7:
            self.state = "weathered"
        else:
            self.state = "intact"


# ---- 自然衰减 ----

def tick_natural_decay(evidence: Evidence, climate_factor: float = 1.0,
                        rng: random.Random | None = None) -> bool:
    """
    对一件证据应用一年的自然衰减。
    climate_factor: >1 加速（潮湿），<1 减慢（干燥/寒冷）。
    返回 True 表示证据被摧毁。
    """
    if evidence.state in ("buried", "destroyed"):
        return False

    if rng is None:
        rng = random.Random()

    base_decay = 1.0
    material_rate = MATERIAL_DECAY_RATE.get(evidence.material, 1.0)
    random_factor = rng.uniform(0.5, 1.5)

    decay = base_decay * material_rate * climate_factor * random_factor
    evidence.current_durability -= decay
    evidence.update_state()
    advance_text_damage(evidence)

    return evidence.state == "destroyed"


def get_climate_factor(biome: str) -> float:
    """根据生物群系返回气候衰减因子。"""
    factors = {
        "river_valley": 1.4,   # 潮湿
        "forest": 1.3,
        "grassland": 1.0,
        "plains": 0.9,
        "scrubland": 0.6,      # 干燥
        "desert": 0.3,         # 极干 → 反而保存
        "highland": 0.8,
        "mountain": 0.7,
        "tundra": 0.2,         # 冻土 → 极好保存
    }
    return factors.get(biome, 1.0)


# ---- 事件驱动摧毁 ----

# 每类摧毁事件对每种材质的存活概率
DESTRUCTION_SURVIVAL = {
    "war_sack": {
        "stone": 0.95, "metal": 0.85, "parchment": 0.15,
        "wood": 0.30, "cloth": 0.10, "oral": 0.60,
    },
    "fire": {
        "stone": 0.90, "metal": 0.80, "parchment": 0.05,
        "wood": 0.10, "cloth": 0.05, "oral": 0.70,
    },
    "flood": {
        "stone": 0.85, "metal": 0.70, "parchment": 0.05,
        "wood": 0.40, "cloth": 0.20, "oral": 0.80,
    },
    "earthquake": {
        "stone": 0.60, "metal": 0.75, "parchment": 0.50,
        "wood": 0.50, "cloth": 0.60, "oral": 0.95,
    },
    "plague": {
        "stone": 1.0, "metal": 1.0, "parchment": 1.0,
        "wood": 1.0, "cloth": 1.0, "oral": 0.80,  # 口述会因人口减少而失传
    },
}


def apply_event_destruction(location_id: str, evidence_dict: dict[str, Evidence],
                             destruction_type: str, rng: random.Random) -> dict:
    """
    对一个地点的所有证据施加事件驱动摧毁。
    返回统计信息 {destroyed, buried, degraded, survived}。
    """
    stats = {"destroyed": 0, "buried": 0, "degraded": 0, "survived": 0}
    survival_table = DESTRUCTION_SURVIVAL.get(destruction_type, {})

    for evd in evidence_dict.values():
        if evd.location_id != location_id:
            continue
        if evd.state in ("buried", "destroyed"):
            continue

        material = evd.material
        survival_chance = survival_table.get(material, 0.5)

        # 副本独立判定
        if evd.is_copy_of:
            survival_chance += 0.1  # 副本不在原地，更可能存活

        if rng.random() < survival_chance:
            # 存活的证据可能降级
            if rng.random() < 0.3:
                evd.current_durability *= rng.uniform(0.5, 0.8)
                evd.update_state()
                advance_text_damage(evd)
                stats["degraded"] += 1
            else:
                stats["survived"] += 1
        else:
            # 被摧毁或埋藏
            if destruction_type in ("earthquake",) and rng.random() < 0.4:
                evd.state = "buried"
                evd.discoverability *= 0.3  # 更难发现
                stats["buried"] += 1
            else:
                evd.state = "destroyed"
                stats["destroyed"] += 1

    return stats


def apply_burial_preservation(location_id: str, evidence_dict: dict[str, Evidence],
                               rng: random.Random) -> int:
    """
    将某地点的部分证据埋藏（如建筑坍塌、火山灰掩埋）。
    返回埋藏数量。
    """
    count = 0
    for evd in evidence_dict.values():
        if evd.location_id != location_id:
            continue
        if evd.state in ("buried", "destroyed"):
            continue
        # 只有特定类型的证据能被埋藏
        if evd.evidence_type in ("structure", "artifact", "document") and rng.random() < 0.2:
            evd.state = "buried"
            evd.discoverability *= 0.3
            count += 1
    return count


# ---- 证据配方表 ----

EVIDENCE_RECIPES = {
    "founding": [
        {"type": "document", "subtype": "founding_charter", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.5},
        {"type": "structure", "subtype": "foundation_stone", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.7},
        {"type": "oral", "subtype": "founding_legend", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.9},
    ],
    "war": [
        {"type": "structure", "subtype": "battlefield_ruins", "location": "near_settlement",
         "material": "stone", "copies": 0, "discoverability": 0.4},
        {"type": "artifact", "subtype": "scattered_weapons", "location": "near_settlement",
         "material": "metal", "copies": 0, "discoverability": 0.3},
        {"type": "document", "subtype": "war_record", "location": "settlement",
         "material": "parchment", "copies": 2, "discoverability": 0.6},
        {"type": "oral", "subtype": "war_song", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
        {"type": "environmental", "subtype": "burn_layer", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.6},
    ],
    "disaster": [
        {"type": "environmental", "subtype": "flood_sediment", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.5},
        {"type": "artifact", "subtype": "damaged_relics", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.4},
        {"type": "oral", "subtype": "survivor_account", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "reconstruction": [
        {"type": "structure", "subtype": "repaired_masonry", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.8},
        {"type": "document", "subtype": "reconstruction_account", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "artifact", "subtype": "reused_fittings", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.35},
    ],
    "relief": [
        {"type": "document", "subtype": "relief_inventory", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.45},
        {"type": "artifact", "subtype": "supply_crate_remains", "location": "settlement",
         "material": "wood", "copies": 0, "discoverability": 0.35},
        {"type": "oral", "subtype": "relief_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "decline": [
        {"type": "structure", "subtype": "abandoned_dwellings", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.8},
        {"type": "environmental", "subtype": "occupation_gap", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.5},
        {"type": "oral", "subtype": "exodus_memory", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "discovery": [
        {"type": "document", "subtype": "research_notes", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "artifact", "subtype": "crafted_item", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.5},
    ],
    "literary_work": [
        {"type": "document", "subtype": "literary_manuscript", "location": "settlement",
         "material": "parchment", "copies": 3, "discoverability": 0.5},
        {"type": "document", "subtype": "literary_commentary", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "oral", "subtype": "popular_recitation", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "literary_spread": [
        {"type": "document", "subtype": "traveling_literary_copy", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.45},
        {"type": "oral", "subtype": "adapted_recitation", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.75},
    ],
    "theoretical_work": [
        {"type": "document", "subtype": "theoretical_treatise", "location": "settlement",
         "material": "parchment", "copies": 2, "discoverability": 0.45},
        {"type": "document", "subtype": "lecture_notes", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "artifact", "subtype": "demonstration_model", "location": "settlement",
         "material": "wood", "copies": 0, "discoverability": 0.4},
    ],
    "cultural": [
        {"type": "structure", "subtype": "temple", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.9},
        {"type": "document", "subtype": "religious_text", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.5},
        {"type": "oral", "subtype": "hymn", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "raid": [
        {"type": "artifact", "subtype": "burned_structures", "location": "settlement",
         "material": "wood", "copies": 0, "discoverability": 0.5},
        {"type": "oral", "subtype": "raid_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "treaty": [
        {"type": "document", "subtype": "treaty_tablet", "location": "settlement",
         "material": "stone", "copies": 1, "discoverability": 0.6},
        {"type": "structure", "subtype": "treaty_pillar", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.7},
        {"type": "oral", "subtype": "oath_of_peace", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "rebellion": [
        {"type": "structure", "subtype": "damaged_buildings", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.6},
        {"type": "document", "subtype": "rebel_manifesto", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.3},
        {"type": "oral", "subtype": "rebellion_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "construction": [
        {"type": "structure", "subtype": "building_remains", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.9},
        {"type": "document", "subtype": "construction_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.5},
        {"type": "artifact", "subtype": "builders_tools", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.3},
    ],
    "trade": [
        {"type": "document", "subtype": "trade_ledger", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "artifact", "subtype": "foreign_coin", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.3},
        {"type": "oral", "subtype": "merchant_tale", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "ruler_change": [
        {"type": "document", "subtype": "succession_decree", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "structure", "subtype": "ruler_tomb", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.7},
        {"type": "oral", "subtype": "succession_gossip", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "population_milestone": [
        {"type": "document", "subtype": "census_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "oral", "subtype": "old_timers_memory", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "economic": [
        {"type": "document", "subtype": "tax_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "artifact", "subtype": "grain_storage_jar", "location": "settlement",
         "material": "stone", "copies": 0, "discoverability": 0.5},
        {"type": "oral", "subtype": "traders_complaint", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "festival": [
        {"type": "artifact", "subtype": "festival_token", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.3},
        {"type": "oral", "subtype": "festival_song", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.9},
    ],
    "notable_birth": [
        {"type": "document", "subtype": "birth_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.3},
        {"type": "oral", "subtype": "birth_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "crime": [
        {"type": "document", "subtype": "trial_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.3},
        {"type": "oral", "subtype": "crime_gossip", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.7},
    ],
    "marriage": [
        {"type": "document", "subtype": "marriage_contract", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "oral", "subtype": "wedding_tale", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "exploration": [
        {"type": "document", "subtype": "exploration_journal", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "oral", "subtype": "explorers_tale", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
    ],
    "omen": [
        {"type": "document", "subtype": "omen_record", "location": "settlement",
         "material": "parchment", "copies": 1, "discoverability": 0.4},
        {"type": "oral", "subtype": "omen_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.9},
    ],
    "duel": [
        {"type": "oral", "subtype": "duel_story", "location": "settlement",
         "material": "oral", "copies": 0, "discoverability": 0.8},
        {"type": "artifact", "subtype": "duel_weapon", "location": "settlement",
         "material": "metal", "copies": 0, "discoverability": 0.2},
    ],
}


# 玩家可见名称只描述物体形态，不直接宣告其历史用途或来源事件。
EVIDENCE_DISPLAY_NAMES_CN = {
    "founding_charter": "带封印的旧羊皮纸",
    "foundation_stone": "刻有符号的基石",
    "founding_legend": "当地流传的古老故事",
    "battlefield_ruins": "散落的石质构件",
    "scattered_weapons": "锈蚀的金属残片",
    "war_record": "制式文书残片",
    "war_song": "当地流传的战争歌谣",
    "burn_layer": "土层中的深色炭灰带",
    "flood_sediment": "异常的细砂沉积层",
    "damaged_relics": "受损的金属器物",
    "survivor_account": "关于灾变的口述片段",
    "repaired_masonry": "新旧石料交错的墙体",
    "reconstruction_account": "带材料数目的修缮账页",
    "reused_fittings": "带二次敲打痕迹的金属件",
    "relief_inventory": "列有多批物资的清单残页",
    "supply_crate_remains": "带重复烙印的木板残片",
    "relief_story": "关于外来车队的口述片段",
    "abandoned_dwellings": "门窗被封堵的房屋遗存",
    "occupation_gap": "夹在建筑层间的稀薄土层",
    "exodus_memory": "关于居民离去的口述片段",
    "research_notes": "带有图示的笔记残页",
    "crafted_item": "工艺特殊的金属制品",
    "literary_manuscript": "装订成册的长篇手稿",
    "literary_commentary": "带大量边注的文书",
    "popular_recitation": "当地反复吟诵的长篇段落",
    "traveling_literary_copy": "带外地装订痕迹的抄本",
    "adapted_recitation": "措辞发生变化的吟诵版本",
    "theoretical_treatise": "带定义和图表的分节论稿",
    "lecture_notes": "按讲次编号的笔记",
    "demonstration_model": "带活动连接件的木制模型",
    "temple": "带雕刻的石质建筑遗存",
    "religious_text": "带重复符号的文书残页",
    "hymn": "当地流传的仪式歌谣",
    "burned_structures": "炭化的木构件",
    "raid_story": "关于一次袭击的口述故事",
    "treaty_tablet": "刻有成列文字的石板",
    "treaty_pillar": "双面刻字的石柱",
    "oath_of_peace": "当地流传的誓词",
    "damaged_buildings": "遭破坏的建筑遗存",
    "rebel_manifesto": "字迹密集的文书残片",
    "rebellion_story": "关于动乱的口述故事",
    "building_remains": "规则排列的建筑基址",
    "construction_record": "带尺寸标记的文书",
    "builders_tools": "成组的金属工具",
    "trade_ledger": "写满数字栏目的账页",
    "foreign_coin": "形制陌生的金属钱币",
    "merchant_tale": "商旅间流传的故事",
    "succession_decree": "带印记的制式文书",
    "ruler_tomb": "带铭文的石质墓葬",
    "succession_gossip": "关于权位更替的传闻",
    "census_record": "按行列书写的名册残页",
    "old_timers_memory": "老人反复讲述的往事",
    "tax_record": "带数字和印记的账页",
    "grain_storage_jar": "带容量刻线的储粮罐",
    "traders_complaint": "商贩间流传的抱怨",
    "festival_token": "带孔的小型金属牌",
    "festival_song": "当地节庆歌谣",
    "birth_record": "简短的登记文书",
    "birth_story": "关于某次出生的故事",
    "trial_record": "分栏书写的审理文书",
    "crime_gossip": "关于案件的街谈巷议",
    "marriage_contract": "带有两组印记的契约",
    "wedding_tale": "当地流传的婚礼故事",
    "exploration_journal": "带路线草图的笔记",
    "explorers_tale": "旅人反复讲述的见闻",
    "omen_record": "带天象图案的记录残页",
    "omen_story": "关于异常天象的故事",
    "duel_story": "关于一场决斗的故事",
    "duel_weapon": "带缺口的单件兵器",
}
EVIDENCE_DISPLAY_NAMES_CN.update({
    subtype: profile.display_name
    for subtype, profile in TECHNOLOGY_BY_SUBTYPE.items()
})


MATERIAL_FEATURE_OPTIONS = {
    "stone": {
        "colors": ["gray_white", "blue_gray", "ochre", "dark_gray"],
        "surfaces": ["coarse_grain", "fine_chisel_marks", "worn_smooth", "jagged_break"],
        "marks": ["mineral_vein", "soil_in_grooves", "thin_moss", "impact_chips"],
    },
    "metal": {
        "colors": ["dark_brown", "black_gray", "rust_red", "mottled_green"],
        "surfaces": ["pitted_corrosion", "hammer_pattern", "blunted_edges", "oxide_crust"],
        "marks": ["force_bend", "parallel_scratches", "remaining_rivet", "fused_soil"],
    },
    "parchment": {
        "colors": ["dark_yellow", "gray_brown", "light_brown", "blackened_ivory"],
        "surfaces": ["visible_fibers", "dry_wrinkles", "brittle_folds", "faint_sheen"],
        "marks": ["insect_holes", "wax_trace", "water_blurred_ink", "missing_fold"],
    },
    "wood": {
        "colors": ["deep_brown", "ash_gray", "char_black", "faded_tan"],
        "surfaces": ["visible_grain", "flaking_surface", "softened_core", "charred_side"],
        "marks": ["joint_holes", "tool_cuts", "ash_in_cracks", "dense_growth_rings"],
    },
    "cloth": {
        "colors": ["faded_indigo", "dark_red_brown", "gray_white", "muted_green"],
        "surfaces": ["frayed_fibers", "regular_weave", "unraveled_edge", "soil_coating"],
        "marks": ["repair_stitches", "round_stain", "geometric_pattern", "dark_fold"],
    },
}


class EvidenceGenerator:
    """根据事件生成证据。"""

    def __init__(self, seed: int):
        self.seed = seed
        self.rng = random.Random(seed + 600)
        self.counter = 0
        self._document_fingerprints: set[str] = set()

    def _next_id(self) -> str:
        self.counter += 1
        return f"evd_{self.counter:04d}"

    def _generate_physical_features(self, evidence_id: str, evidence_type: str,
                                    subtype: str, material: str,
                                    is_copy: bool = False) -> dict:
        """生成不依赖历史真相的稳定观察特征。"""
        base_subtype = subtype.removesuffix("_copy") if is_copy else subtype
        rng = random.Random(
            f"{self.seed}|{evidence_id}|{evidence_type}|{subtype}|{material}")
        display_name = EVIDENCE_DISPLAY_NAMES_CN.get(
            base_subtype, base_subtype.replace("_", " "))

        if evidence_type == "oral":
            return {
                "display_name": display_name,
                "tags": [
                    "material:oral",
                    "delivery:" + rng.choice([
                        "hesitant", "variant_wording", "rhythmic", "elder_only",
                    ]),
                    "variation:" + rng.choice([
                        "names_and_numbers", "divergent_ending",
                        "place_without_date", "stable_core_unclear_cause",
                    ]),
                ],
            }

        options = MATERIAL_FEATURE_OPTIONS.get(material, {
            "colors": ["unknown"],
            "surfaces": ["indistinct"],
            "marks": ["no_clear_mark"],
        })
        dimension_options = {
            "document": ["palm_fragment", "two_joining_sheets", "short_roll", "single_corner"],
            "artifact": ["one_hand", "forearm_length", "several_fragments", "larger_than_palm"],
            "structure": ["knee_high", "several_paces", "foundation_only", "large_blocks"],
            "environmental": ["narrow_band", "two_fingers_thick", "intermittent_patch", "between_layers"],
        }
        tags = [
            f"material:{material}",
            "color:" + rng.choice(options["colors"]),
            "surface:" + rng.choice(options["surfaces"]),
            "scale:" + rng.choice(dimension_options.get(
                evidence_type, ["unknown"])),
            "mark:" + rng.choice(options["marks"]),
        ]
        features = {
            "display_name": display_name,
            "tags": tags,
        }

        if evidence_type == "document":
            if base_subtype in PUBLIC_INSCRIPTION_SUBTYPES:
                tags.extend([
                    "script:monumental_letters",
                    "legibility:clear_large_letters",
                    "visibility:public_inscription",
                ])
            else:
                tags.extend([
                    "script:" + rng.choice([
                        "narrow_rows", "hurried_hand", "margin_note",
                        "ruled_columns",
                    ]),
                    "legibility:" + rng.choice([
                        "isolated_glyphs", "numbers_and_symbols",
                        "missing_ends", "seal_area_clear",
                    ]),
                ])
        elif evidence_type == "artifact":
            technology = TECHNOLOGY_BY_SUBTYPE.get(base_subtype)
            if technology is not None:
                tags.extend([
                    "form:" + technology.form_code,
                    "mechanism:" + technology.mechanism_code,
                ])
            else:
                tags.append("form:" + rng.choice([
                    "asymmetric", "riveted_parts", "worn_edges", "mounting_socket",
                ]))
        elif evidence_type == "structure":
            tags.append("arrangement:" + rng.choice([
                "aligned", "hardened_mortar", "wide_base", "different_orientation",
            ]))
            if base_subtype in PUBLIC_INSCRIPTION_SUBTYPES:
                tags.extend([
                    "script:monumental_letters",
                    "legibility:clear_large_letters",
                    "visibility:public_inscription",
                ])
        elif evidence_type == "environmental":
            tags.append("stratigraphy:" + rng.choice([
                "charcoal_and_bone", "uniform_grains",
                "thicker_by_wall", "pottery_and_metal",
            ]))

        return features

    def _generate_unique_written_content(self, event, subtype: str,
                                         evidence_id: str) -> dict:
        """Generate an original whose full wording is unique in this world."""
        for variant in range(256):
            written = build_written_content(
                event, subtype, self.seed, evidence_id, variant=variant)
            text = "\n".join(
                passage.get("text", "") for passage in written["passages"])
            fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if fingerprint not in self._document_fingerprints:
                self._document_fingerprints.add(fingerprint)
                return written
        raise RuntimeError(
            f"could not generate unique document text for {evidence_id}")

    def _generate_unique_written_copy(self, source_content: dict,
                                      evidence_id: str, copy_index: int,
                                      created_year: int) -> dict:
        """Derive a copy that cannot collide with another stored carrier."""
        for variant in range(256):
            written = build_written_copy_content(
                source_content, self.seed, evidence_id, copy_index,
                created_year, variant=variant)
            text = "\n".join(
                passage.get("text", "") for passage in written["passages"])
            fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if fingerprint not in self._document_fingerprints:
                self._document_fingerprints.add(fingerprint)
                return written
        raise RuntimeError(
            f"could not generate unique copied text for {evidence_id}")

    def create_evidence_for_event(self, event,
                                  source_records: dict | None = None
                                  ) -> list[Evidence]:
        recipes = EVIDENCE_RECIPES.get(event.event_type, [])
        evidence_list = []
        source_records = source_records or {}

        for recipe in recipes:
            subtype = recipe["subtype"]
            material = recipe["material"]
            if event.event_type == "discovery" and subtype == "crafted_item":
                subtype = event.details.get("artifact_subtype", subtype)
                material = event.details.get("artifact_material", material)
            durability = MATERIAL_DURABILITY.get(material, 50)
            evidence_id = self._next_id()
            records = source_records.get(recipe["subtype"], [])
            record = records[0] if records else None
            content_data = {}
            is_written_carrier = (
                recipe["type"] == "document"
                or subtype in PUBLIC_INSCRIPTION_SUBTYPES)
            retained_claim_ids = (
                [claim.id for claim in record.claimed_facts] if record else [])
            evidence = Evidence(
                id=evidence_id,
                event_id=event.id,
                evidence_type=recipe["type"],
                subtype=subtype,
                location_type=recipe["location"],
                location_id=event.primary_location,
                created_year=event.year,
                material=material,
                max_durability=durability,
                current_durability=durability,
                state="intact",
                source_record_id=record.id if record else None,
                source_event_ids=[event.id],
                discoverability=recipe.get("discoverability", 0.5),
                content_data=content_data,
                narrative_bias=(record.perspective if record else
                                event.narrative_bias
                                if event.narrative_bias != "neutral" else
                                self._determine_bias(recipe["type"])),
                physical_features=self._generate_physical_features(
                    evidence_id, recipe["type"], subtype,
                    material, is_copy=False),
                retained_claim_ids=retained_claim_ids,
                provenance_clues={
                    "estimated_year_range": [event.year - 3, event.year + 3],
                    "origin_location_id": event.primary_location,
                    "carrier_subtype": subtype,
                },
                origin_location_id=event.primary_location,
                owner_type="settlement",
                owner_id=event.primary_location,
            )
            if is_written_carrier:
                initialize_text_plan(evidence, self.seed)
            if subtype in PUBLIC_INSCRIPTION_SUBTYPES:
                prepare_materialized_carrier(
                    evidence,
                    self._generate_unique_written_content(
                        event, subtype, evidence_id),
                )
            evidence_list.append(evidence)

            for copy_index in range(recipe.get("copies", 0)):
                copy_id = self._next_id()
                copy_subtype = subtype + "_copy"
                copy_record = (
                    records[copy_index + 1]
                    if copy_index + 1 < len(records) else record)
                copy_claim_ids = (
                    [claim.id for claim in copy_record.claimed_facts]
                    if copy_record else [])
                copy_year = (copy_record.created_year if copy_record else
                             event.year + self.rng.randint(1, 10))
                copy_content_data = {}
                copy = Evidence(
                    id=copy_id,
                    event_id=event.id,
                    evidence_type=recipe["type"],
                    subtype=copy_subtype,
                    location_type=recipe["location"],
                    location_id=event.primary_location,
                    created_year=copy_year,
                    material=material,
                    max_durability=durability,
                    current_durability=durability,
                    state="intact",
                    source_record_id=copy_record.id if copy_record else None,
                    source_event_ids=[event.id],
                    is_copy_of=evidence.id,
                    discoverability=recipe.get("discoverability", 0.5) * 0.7,
                    content_data=copy_content_data,
                    narrative_bias=evidence.narrative_bias,
                    physical_features=self._generate_physical_features(
                        copy_id, recipe["type"], copy_subtype,
                        material, is_copy=True),
                    retained_claim_ids=copy_claim_ids,
                    provenance_clues={
                        "estimated_year_range": [event.year - 1, event.year + 12],
                        "origin_location_id": event.primary_location,
                        "carrier_subtype": copy_subtype,
                        "copy_status": "probable_copy",
                    },
                    contamination=["copyist_variation"],
                    authenticity="copy",
                    origin_location_id=event.primary_location,
                    owner_type="settlement",
                    owner_id=event.primary_location,
                )
                if is_written_carrier:
                    initialize_text_plan(
                        copy, self.seed, copy_index=copy_index)
                if subtype in PUBLIC_INSCRIPTION_SUBTYPES:
                    copy_written = self._generate_unique_written_copy(
                        evidence.content_data["written_content"],
                        copy_id, copy_index, copy_year)
                    prepare_materialized_carrier(
                        copy, copy_written,
                        parent_written=evidence.content_data["written_content"])
                evidence_list.append(copy)

        return evidence_list

    def _determine_bias(self, evidence_type: str) -> str:
        bias_map = {
            "document": "official",
            "structure": "neutral",
            "artifact": "neutral",
            "oral": "folk",
            "environmental": "neutral",
        }
        return bias_map.get(evidence_type, "neutral")
