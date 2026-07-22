"""
事件系统：从模拟状态转移中检测并生成历史事件。
重要约定：participants 始终存 settlement_id，不存名称。名称在 title/details 中。
Phase 2: 增加因果链、结构化影响、压力快照。
"""

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HistoricalEvent:
    """一个历史事件。participants 始终为 settlement_id 列表。"""
    id: str
    year: int
    event_type: str
    title: str
    severity: float
    primary_location: str  # settlement_id
    participants: list[str] = field(default_factory=list)  # 始终是 settlement_id
    person_ids: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    narrative_bias: str = "neutral"

    # 版本
    schema_version: int = 3

    # ---- Phase 2 新增：因果与结构化影响 ----
    cause_event_ids: list[str] = field(default_factory=list)
        # 直接前置事件 ID
    effect_ids: list[str] = field(default_factory=list)
        # 应用的 Effect ID（由 EffectResolver 跟踪）
    effects: list[dict] = field(default_factory=list)
        # 可持久化的结构化 Effect 内容，用于审计和重放
    trigger_factors: dict[str, float] = field(default_factory=dict)
        # 触发时的压力和分数快照，用于 debug
        # e.g. {"unrest_pressure": 0.72, "famine_contribution": 0.45}
    process_id: Optional[str] = None
        # 所属的跨年历史过程
    importance_score: float = 0.0
        # 综合历史重要度
    visibility_score: float = 0.0
        # 当时有多少人可能知道 [0, 1]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "year": self.year,
            "event_type": self.event_type,
            "title": self.title,
            "severity": self.severity,
            "primary_location": self.primary_location,
            "participants": list(self.participants),
            "person_ids": list(self.person_ids),
            "details": dict(self.details),
            "narrative_bias": self.narrative_bias,
            "cause_event_ids": list(self.cause_event_ids),
            "effect_ids": list(self.effect_ids),
            "effects": [dict(effect) for effect in self.effects],
            "trigger_factors": dict(self.trigger_factors),
            "process_id": self.process_id,
            "importance_score": self.importance_score,
            "visibility_score": self.visibility_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricalEvent":
        return cls(
            id=data["id"],
            year=data["year"],
            event_type=data["event_type"],
            title=data["title"],
            severity=data.get("severity", 0.0),
            primary_location=data["primary_location"],
            participants=data.get("participants", []),
            person_ids=data.get("person_ids", []),
            details=data.get("details", {}),
            narrative_bias=data.get("narrative_bias", "neutral"),
            schema_version=data.get("schema_version", 1),
            cause_event_ids=data.get("cause_event_ids", []),
            effect_ids=data.get("effect_ids", []),
            effects=[dict(effect) for effect in data.get("effects", [])],
            trigger_factors=data.get("trigger_factors", {}),
            process_id=data.get("process_id"),
            importance_score=data.get("importance_score", 0.0),
            visibility_score=data.get("visibility_score", 0.0),
        )


class EventGenerator:

    def __init__(self, seed: int):
        self.rng = random.Random(seed + 500)
        self.counter = 0

    def _next_id(self) -> str:
        self.counter += 1
        return f"event_{self.counter:04d}"

    # ==================== 建城 ====================

    def generate_founding_event(self, settlement_id: str, settlement_name: str,
                                 year: int, founder_name: str,
                                 founder_id: str | None = None) -> HistoricalEvent:
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="founding",
            title=f"建立{settlement_name}",
            severity=0.3,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[founder_id] if founder_id else [],
            details={
                "settlement_name": settlement_name,
                "founder": founder_name,
                "founder_id": founder_id,
                "description_cn": f"{year}年，{founder_name}带领追随者在{settlement_name}定居，建立了这座聚落。",
            },
        )

    # ==================== 战争 / 袭击 / 条约 / 叛乱 ====================

    def generate_war_event(self, year: int,
                            attacker_id: str, attacker_name: str,
                            defender_id: str, defender_name: str,
                            location_id: str,
                            outcome: str = "attacker_victory") -> HistoricalEvent:
        titles = {
            "attacker_victory": f"{attacker_name}攻陷{defender_name}",
            "defender_victory": f"{defender_name}击退{attacker_name}",
            "stalemate": f"{attacker_name}与{defender_name}之战",
        }
        descs = {
            "attacker_victory": f"{year}年，经过数月围城，{attacker_name}的军队攻陷了{defender_name}。城市被洗劫，大量居民流离失所。",
            "defender_victory": f"{year}年，{defender_name}的守军顽强抵抗，成功击退了{attacker_name}的进攻。城墙上的箭痕至今仍在。",
            "stalemate": f"{year}年，{attacker_name}与{defender_name}之间爆发了一场激战。双方伤亡惨重，但都未能取得决定性胜利。",
        }
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="war",
            title=titles.get(outcome, titles["stalemate"]),
            severity={"attacker_victory": 0.9, "defender_victory": 0.6, "stalemate": 0.7}[outcome],
            primary_location=location_id,
            participants=[attacker_id, defender_id],
            details={
                "attacker": attacker_name, "defender": defender_name,
                "outcome": outcome,
                "description_cn": descs.get(outcome, descs["stalemate"]),
            },
        )

    def generate_raid_event(self, year: int,
                             raider_id: str, raider_name: str,
                             target_id: str, target_name: str,
                             location_id: str) -> HistoricalEvent:
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="raid",
            title=f"{raider_name}袭击{target_name}边境",
            severity=0.35,
            primary_location=location_id,
            participants=[raider_id, target_id],
            details={
                "raider": raider_name, "target": target_name,
                "description_cn": f"{year}年，{raider_name}的劫掠队袭击了{target_name}的边境村庄——牲畜被夺、房屋被烧，但没有攻入主城。",
            },
        )

    def generate_treaty_event(self, year: int,
                               side_a_id: str, side_a_name: str,
                               side_b_id: str, side_b_name: str,
                               location_id: str,
                               treaty_type: str = "peace") -> HistoricalEvent:
        if treaty_type == "peace":
            title = f"{side_a_name}与{side_b_name}签订和约"
            desc = f"{year}年，{side_a_name}与{side_b_name}签署了和平条约，结束了双方之间的敌对状态。"
        elif treaty_type == "alliance":
            title = f"{side_a_name}与{side_b_name}结盟"
            desc = f"{year}年，{side_a_name}与{side_b_name}正式结为同盟，承诺在战争中相互支援。"
        else:
            title = f"{side_a_name}与{side_b_name}缔约"
            desc = f"{year}年，{side_a_name}与{side_b_name}达成了一项重要协议。"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="treaty",
            title=title, severity=0.4,
            primary_location=location_id,
            participants=[side_a_id, side_b_id],
            details={"treaty_type": treaty_type, "description_cn": desc},
        )

    def generate_rebellion_event(self, year: int,
                                  settlement_id: str, settlement_name: str,
                                  cause: str = "overtaxation") -> HistoricalEvent:
        causes = {
            "overtaxation": "不堪重税",
            "famine": "饥荒引发的民变",
            "succession": "继承权之争",
            "religious": "宗教冲突",
        }
        cause_cn = causes.get(cause, causes["overtaxation"])
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="rebellion",
            title=f"{settlement_name}叛乱",
            severity=0.55,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={
                "cause": cause,
                "description_cn": f"{year}年，{settlement_name}爆发了因{cause_cn}引发的叛乱。暴动持续了数周才被平息，城市遭受了相当的破坏。",
            },
        )

    # ==================== 灾难 ====================

    def generate_disaster_event(self, year: int,
                                 settlement_id: str, settlement_name: str,
                                 disaster_type: str = "flood") -> HistoricalEvent:
        type_names = {
            "flood": ("洪水", f"{year}年，河水暴涨，一场大洪水袭击了{settlement_name}，淹没了低洼地区的房屋和农田。"),
            "fire": ("大火", f"{year}年，一场毁灭性的大火吞噬了{settlement_name}——干燥的天气和大风让火势迅速蔓延，多座重要建筑化为灰烬。"),
            "plague": ("瘟疫", f"{year}年，一种可怕的疾病在{settlement_name}蔓延开来。死者如此之多，以至于来不及逐一安葬。"),
            "earthquake": ("地震", f"{year}年，大地剧烈震颤。{settlement_name}的建筑大量倒塌，幸存者在废墟中挖掘了数日。"),
            "drought": ("旱灾", f"{year}年的漫长干旱让{settlement_name}周围的河流几近枯竭。庄稼在田里干枯，饥荒的阴影笼罩了整座城市。"),
            "storm": ("暴风雨", f"{year}年，一场罕见的暴风雨席卷了{settlement_name}，掀翻屋顶、吹倒树木，港口船只遭受重创。"),
        }
        cn_name, desc = type_names.get(disaster_type, type_names["flood"])
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="disaster",
            title=f"{settlement_name}{cn_name}",
            severity=0.7,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"disaster_type": disaster_type, "description_cn": desc},
        )

    def generate_reconstruction_event(self, year: int, settlement_id: str,
                                      settlement_name: str,
                                      building_type: str,
                                      building_name: str) -> HistoricalEvent:
        desc = (
            f"{year}年，{settlement_name}开始修复灾害中受损的{building_name}。"
            "工程使用了回收材料，并由当地财政支付。"
        )
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="reconstruction",
            title=f"{settlement_name}重建{building_name}", severity=0.25,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={
                "building_type": building_type,
                "building_name": building_name,
                "description_cn": desc,
            },
            importance_score=0.25, visibility_score=0.6,
        )

    def generate_relief_event(self, year: int,
                              recipient_id: str, recipient_name: str,
                              donor_id: str, donor_name: str) -> HistoricalEvent:
        desc = (
            f"{year}年，{donor_name}向受灾的{recipient_name}送去粮食、木料和资金。"
            "这些物资缓解了当地的短缺，并帮助修复公共设施。"
        )
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="relief",
            title=f"{donor_name}援助{recipient_name}", severity=0.30,
            primary_location=recipient_id,
            participants=[recipient_id, donor_id],
            details={
                "recipient_name": recipient_name,
                "donor_name": donor_name,
                "description_cn": desc,
            },
            importance_score=0.30, visibility_score=0.7,
        )

    def generate_decline_event(self, year: int, settlement_id: str,
                               settlement_name: str) -> HistoricalEvent:
        desc = (
            f"{year}年，{settlement_name}仍未从先前的灾害中恢复。"
            "受损街区继续荒废，一部分居民迁往别处。"
        )
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="decline",
            title=f"{settlement_name}灾后衰落", severity=0.45,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"description_cn": desc},
            importance_score=0.45, visibility_score=0.7,
        )

    def generate_literary_spread_event(
            self, year: int, source_id: str, source_name: str,
            target_id: str, target_name: str, work_title: str,
            author_name: str) -> HistoricalEvent:
        desc = (
            f"{year}年，《{work_title}》的抄本从{source_name}传入{target_name}。"
            f"当地抄写者保留了作者{author_name}的署名，并增加了少量边注。"
        )
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="literary_spread",
            title=f"《{work_title}》传入{target_name}", severity=0.14,
            primary_location=target_id,
            participants=[source_id, target_id],
            details={
                "source_name": source_name,
                "target_name": target_name,
                "work_title": work_title,
                "author_name": author_name,
                "description_cn": desc,
            },
            importance_score=0.14, visibility_score=0.5,
        )

    # ==================== 技术/文化发现 ====================

    def generate_discovery_event(self, year: int, settlement_id: str,
                                   discovery_name: str, description: str) -> HistoricalEvent:
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="discovery",
            title=discovery_name,
            severity=0.25,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"discovery_name": discovery_name, "description_cn": description},
        )

    # ==================== 日常 pulse 事件 ====================

    def generate_construction_event(self, year: int,
                                     settlement_id: str, settlement_name: str,
                                     building_type: str) -> HistoricalEvent:
        buildings = {
            "temple": ("神殿", f"{year}年，{settlement_name}建起了一座宏伟的神殿。它的石柱上雕刻着精美的纹饰，成为城中信徒聚集的中心。"),
            "library": ("图书馆", f"{year}年，{settlement_name}的学者们建立了一座图书馆，开始系统性地收集和抄录各类典籍。"),
            "market": ("大市场", f"{year}年，{settlement_name}新建了一座大型市场，商贾云集，来自各地的货物在此交易。"),
            "fortification": ("城墙加固", f"{year}年，{settlement_name}大规模加固了城墙和防御工事，城市的安全性大为提升。"),
            "aqueduct": ("引水渠", f"{year}年，{settlement_name}修建了一条引水渠，将远处山泉的清水引入城中。"),
            "palace": ("领主大厅", f"{year}年，{settlement_name}的统治者建造了一座新的领主大厅，以彰显城市的繁荣与权力。"),
        }
        cn_name, desc = buildings.get(building_type, buildings["temple"])
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="construction",
            title=f"{settlement_name}建成{cn_name}",
            severity=0.2,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"building_type": building_type, "description_cn": desc},
        )

    def generate_trade_event(self, year: int,
                              settlement_a_id: str, settlement_a_name: str,
                              settlement_b_id: str, settlement_b_name: str) -> HistoricalEvent:
        goods_list = ["谷物和木材", "铁器和武器", "陶器和纺织品", "香料和染料", "马匹和皮革", "宝石和贵金属"]
        goods = self.rng.choice(goods_list)
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="trade",
            title=f"{settlement_a_name}与{settlement_b_name}开通商路",
            severity=0.15,
            primary_location=settlement_a_id,
            participants=[settlement_a_id, settlement_b_id],
            details={
                "goods": goods,
                "description_cn": f"{year}年，{settlement_a_name}与{settlement_b_name}之间的商路正式开通，两地开始定期交易{goods}。",
            },
        )

    def generate_ruler_change_event(self, year: int,
                                     settlement_id: str, settlement_name: str,
                                     old_ruler: str, new_ruler: str,
                                     change_type: str = "death",
                                     old_ruler_id: str | None = None,
                                     new_ruler_id: str | None = None) -> HistoricalEvent:
        if change_type == "death":
            desc = f"{year}年，{settlement_name}的领主{old_ruler}去世。{new_ruler}继承了统治权。"
            title = f"{settlement_name}领主{old_ruler}去世"
        else:
            desc = f"{year}年，{settlement_name}的统治权从{old_ruler}转移到了{new_ruler}手中。"
            title = f"{settlement_name}政权更替"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="ruler_change",
            title=title, severity=0.3,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[person_id for person_id in
                        (old_ruler_id, new_ruler_id) if person_id],
            details={
                "old_ruler": old_ruler, "new_ruler": new_ruler,
                "old_ruler_id": old_ruler_id,
                "new_ruler_id": new_ruler_id,
                "description_cn": desc,
            },
        )

    def generate_population_milestone(self, year: int,
                                       settlement_id: str, settlement_name: str,
                                       milestone: int) -> HistoricalEvent:
        if milestone >= 1000:
            desc = f"{year}年，{settlement_name}的人口突破了{milestone}人，从小镇发展成了一座像样的城市。"
        elif milestone >= 500:
            desc = f"{year}年，{settlement_name}的人口达到了{milestone}人，村庄已经变成了热闹的城镇。"
        else:
            desc = f"{year}年，{settlement_name}的人口增长到了{milestone}人。"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="population_milestone",
            title=f"{settlement_name}人口达{milestone}",
            severity=0.1,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"milestone": milestone, "description_cn": desc},
        )

    def generate_economic_event(self, year: int,
                                 settlement_id: str, settlement_name: str,
                                 event_type: str) -> HistoricalEvent:
        if event_type == "boom":
            title = f"{settlement_name}的繁荣期"
            desc = f"{year}年前后，{settlement_name}经历了一段罕见的繁荣——连续的丰收加之贸易路线的拓展，让城市积累了可观的财富。"
        else:
            title = f"{settlement_name}的歉收"
            desc = f"{year}年，{settlement_name}遭遇了严重的粮食歉收。虽然没有演变成饥荒，但粮价飞涨，普通民众的日子变得艰难。"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="economic",
            title=title, severity=0.2,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"economic_type": event_type, "description_cn": desc},
        )

    def generate_festival_event(self, year: int,
                                 settlement_id: str, settlement_name: str) -> HistoricalEvent:
        festivals = [
            ("丰收节", f"{year}年，{settlement_name}举行了盛大的丰收庆典。街道上挂满了彩带，人们载歌载舞，庆祝又一个丰年的到来。"),
            ("建国纪念", f"{year}年，{settlement_name}举办了建国周年庆典。游行的队伍穿过城市，诗人吟唱着先祖的功绩。"),
            ("神殿奠基", f"{year}年，{settlement_name}为一座新的神殿举行了奠基仪式。祭司们进行了庄严的祈福，全城居民都前来观礼。"),
        ]
        name, desc = self.rng.choice(festivals)
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="festival",
            title=f"{settlement_name}{name}",
            severity=0.1,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"description_cn": desc},
        )

    # ==================== Phase 2 新增：纹理事件 ====================

    def generate_notable_birth(self, year: int, settlement_id: str,
                                settlement_name: str, person_name: str,
                                parent_name: str,
                                person_id: str | None = None,
                                parent_id: str | None = None) -> HistoricalEvent:
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="notable_birth",
            title=f"{person_name}在{settlement_name}出生",
            severity=0.05,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[person for person in (person_id, parent_id) if person],
            details={
                "person_name": person_name, "parent_name": parent_name,
                "person_id": person_id, "parent_id": parent_id,
                "description_cn": f"{year}年，{parent_name}的家中迎来新生儿{person_name}。登记簿记录了孩子与家属的姓名。",
            },
        )

    def generate_crime_event(self, year: int, settlement_id: str,
                              settlement_name: str) -> HistoricalEvent:
        crimes = [
            ("theft", "大盗窃案", f"{year}年，{settlement_name}发生了一起大盗窃案，失物与去向随后被分别登记。"),
            ("attempted_assassination", "暗杀未遂", f"{year}年，有人在{settlement_name}的集市上试图暗杀当地的税务官。刺客虽然被擒，但幕后主使始终未能查明。"),
            ("smuggling_raid", "走私团伙覆灭", f"{year}年，{settlement_name}的守卫捣毁了一个长期走私违禁药材的团伙。"),
        ]
        crime_type, name, desc = self.rng.choice(crimes)
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="crime",
            title=f"{settlement_name}{name}",
            severity=0.08,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"crime_type": crime_type, "description_cn": desc},
        )

    def generate_marriage_event(self, year: int, settlement_id: str,
                                 settlement_name: str, person_a: str,
                                 person_b: str, marriage_type: str = "political",
                                 person_a_id: str | None = None,
                                 person_b_id: str | None = None) -> HistoricalEvent:
        if marriage_type == "political":
            desc = f"{year}年，{settlement_name}的{person_a}与{person_b}缔结了政治婚姻。这场联姻巩固了两家之间的联盟。"
            title = f"{person_a}与{person_b}联姻"
        else:
            desc = f"{year}年，{settlement_name}举行了一场盛大的婚礼——{person_a}与{person_b}的结合成为全城的话题。"
            title = f"{person_a}与{person_b}成婚"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="marriage",
            title=title, severity=0.08,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[person for person in
                        (person_a_id, person_b_id) if person],
            details={
                "person_a_id": person_a_id,
                "person_b_id": person_b_id,
                "description_cn": desc,
            },
        )

    def generate_exploration_event(self, year: int, settlement_id: str,
                                    settlement_name: str, discoverer: str,
                                    discoverer_id: str | None = None) -> HistoricalEvent:
        findings = [
            ("新矿脉", f"{year}年，{discoverer}在{settlement_name}附近的山中发现了一条新的铁矿矿脉。"),
            ("古代遗迹", f"{year}年，{discoverer}在{settlement_name}外围的密林里发现了一处更古老的文明遗迹。"),
            ("新水源", f"{year}年，{discoverer}在{settlement_name}以北三日路程处发现了一个巨大的淡水湖。"),
            ("隘口通道", f"{year}年，{discoverer}找到了一条穿越山脉的秘密隘口，大大缩短了{settlement_name}与外界的交通。"),
        ]
        name, desc = self.rng.choice(findings)
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="exploration",
            title=f"{settlement_name}发现{name}",
            severity=0.12,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[discoverer_id] if discoverer_id else [],
            details={
                "discoverer_id": discoverer_id,
                "discoverer_name": discoverer,
                "description_cn": desc,
            },
        )

    def generate_omen_event(self, year: int, settlement_id: str,
                             settlement_name: str) -> HistoricalEvent:
        omens = [
            ("彗星", f"{year}年，一颗明亮的彗星划过{settlement_name}的夜空。祭司们对此争论不休——有人说是吉兆，有人说是灾祸的预兆。"),
            ("日食", f"{year}年，白昼突然变成黑夜。{settlement_name}的居民惊恐万分，认为这是诸神发怒的信号。"),
            ("双彩虹", f"{year}年，暴风雨之后，{settlement_name}的天空出现了罕见的双彩虹。人们相信这是先祖的祝福。"),
        ]
        name, desc = self.rng.choice(omens)
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="omen",
            title=f"{settlement_name}出现{name}",
            severity=0.06,
            primary_location=settlement_id,
            participants=[settlement_id],
            details={"description_cn": desc},
        )

    def generate_duel_event(self, year: int, settlement_id: str,
                             settlement_name: str, fighter_a: str,
                             fighter_b: str, cause: str,
                             fighter_a_id: str | None = None,
                             fighter_b_id: str | None = None) -> HistoricalEvent:
        desc = f"{year}年，{fighter_a}与{fighter_b}在{settlement_name}进行了一场决斗，起因是{cause}。"
        return HistoricalEvent(
            id=self._next_id(), year=year, event_type="duel",
            title=f"{fighter_a}与{fighter_b}的决斗",
            severity=0.08,
            primary_location=settlement_id,
            participants=[settlement_id],
            person_ids=[person for person in
                        (fighter_a_id, fighter_b_id) if person],
            details={
                "fighter_a_id": fighter_a_id,
                "fighter_b_id": fighter_b_id,
                "description_cn": desc,
            },
        )
