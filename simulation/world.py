"""
World：顶层世界容器。
编排地理生成 → 聚落放置 → 模拟循环 → 事件检测 → 证据生成。
Phase 2: 分阶段年度循环 + 规则驱动事件 + 压力系统 + 因果链。
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional, Any

import networkx as nx

from config import GRID_WIDTH, GRID_HEIGHT, SIM_YEARS, INITIAL_SETTLEMENT_COUNT
from simulation.geography import Geography, pick_settlement_sites
from simulation.settlement import Settlement, SettlementManager
from simulation.person import Person, PersonManager
from simulation.informants import (
    Informant, InformantManager, KnowledgeEntry,
)
from simulation.events import HistoricalEvent, EventGenerator
from simulation.evidence import (
    EVIDENCE_RECIPES, Evidence, EvidenceGenerator,
    tick_natural_decay, apply_event_destruction, apply_burial_preservation, get_climate_factor
)
from simulation.records import HistoricalRecord, RecordGenerator
from simulation.storage import StorageManager, StorageSite
from simulation.written_content import (
    build_written_content,
    build_written_copy_content,
)
from simulation.pressures import compute_all_pressures, tick_economy
from simulation.event_rules import EventRuleRegistry, EventRuleResult
from simulation.effects import (
    ChangeRuler,
    DamageBuilding,
    DestroySettlement,
    EffectResolver,
    ModifyFoodStock,
    ModifyInfrastructure,
    ModifyCulturalInfluence,
    ModifyLegitimacy,
    ModifyPopulation,
    ModifyRelationship,
    ModifyStability,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
    ModifyTreasury,
    TransferControl,
    effect_to_dict,
)


DISASTER_RECOVERY_FOCUS = {
    "flood": ("market", "市场与排水沟"),
    "fire": ("market", "烧毁的公共建筑"),
    "drought": ("aqueduct", "引水设施"),
    "storm": ("market", "受损屋顶与市场"),
    "earthquake": ("fortification", "城墙和承重结构"),
}

LITERARY_TITLES = {
    "epic": ["七座城门之歌", "灰河远征记", "守夜者长歌", "群山之后"],
    "drama": ["空王座", "两枚印记", "雨夜城门", "最后一盏灯"],
    "chronicle": ["石墙编年", "河谷诸年记", "旧市纪事", "八任执政者记"],
    "lyric_cycle": ["十二月歌", "井边短章", "风过麦田", "远路与归人"],
}

THEORETICAL_TITLES = {
    "mechanics": ["重物、支点与绳索论", "轮轴比例考", "落体与斜面札论"],
    "agronomy": ["土性与轮作论", "谷种选择考", "水渠、坡地与收成"],
    "medicine": ["脉息与热病辨", "创伤清洗论", "草药配伍考"],
    "astronomy": ["行星周期表解", "影长与季节论", "星位观测法"],
}

TECHNOLOGY_TITLES = [
    "改良滑轮组", "深沟轮作法", "封闭式蓄水槽", "标准化药材秤",
    "齿轮传动架", "双层炉膛", "石拱承重法", "星位定向仪",
]


@dataclass
class World:
    """世界容器。"""
    seed: int
    name: str = "Unknown World"
    current_year: int = 0

    geography: Optional[Geography] = None
    settlements: dict[str, Settlement] = field(default_factory=dict)
    events: list[HistoricalEvent] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    records: dict[str, HistoricalRecord] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    informants: dict[str, Informant] = field(default_factory=dict)
    knowledge_entries: dict[str, KnowledgeEntry] = field(default_factory=dict)
    storage_sites: dict[str, StorageSite] = field(default_factory=dict)
    event_history_by_settlement: dict[str, list[str]] = field(default_factory=dict)

    _settlement_mgr: Optional[SettlementManager] = None
    _event_gen: Optional[EventGenerator] = None
    _evidence_gen: Optional[EvidenceGenerator] = None
    _record_gen: Optional[RecordGenerator] = None
    _person_mgr: Optional[PersonManager] = None
    _informant_mgr: Optional[InformantManager] = None
    _storage_mgr: Optional[StorageManager] = None

    # 追踪状态
    _last_ruler_change: dict[str, int] = field(default_factory=dict)
    _pop_milestones: dict[str, int] = field(default_factory=dict)
    _recent_war_years: dict[str, int] = field(default_factory=dict)  # "a|b" -> last war year
    _pending_war_settlements: list[tuple[str, int, str]] = field(default_factory=list)
    _pending_disaster_aftermaths: list[tuple[str, int, str, str]] = field(
        default_factory=list)
    _pending_literary_spreads: list[tuple[str, int, str]] = field(
        default_factory=list)

    # Phase 2 新增
    debug_causes: bool = False
    _rule_registry: Any = None
    _effect_resolver: Any = None
    _pressures_cache: dict[str, dict[str, float]] = field(default_factory=dict)
    _rule_cooldowns: dict[str, dict[str, int]] = field(default_factory=dict)
        # {event_type: {settlement_id: last_trigger_year}}
    _state_cause_sources: dict[str, dict[str, dict]] = field(default_factory=dict)
        # {settlement_id: {state_dimension: {event_id, direction}}}

    def generate(self, years: int = SIM_YEARS):
        rng = random.Random(self.seed)
        self.geography = Geography(self.seed)
        self._settlement_mgr = SettlementManager(self.seed)
        self._event_gen = EventGenerator(self.seed)
        self._evidence_gen = EvidenceGenerator(self.seed)
        self._record_gen = RecordGenerator(self.seed)
        self._person_mgr = PersonManager(self.seed)
        self._informant_mgr = InformantManager(
            self.seed, self.informants, self.knowledge_entries)
        self._storage_mgr = StorageManager(self.seed, self.storage_sites)

        # Phase 2: 初始化规则与效果系统
        self._rule_registry = EventRuleRegistry()
        self._effect_resolver = EffectResolver(self.seed)

        # Step 1: 生成地理
        self.geography.generate()

        # Step 2: 放置初始聚落
        sites = pick_settlement_sites(
            self.geography.suitability, INITIAL_SETTLEMENT_COUNT, self.seed)
        for x, y in sites:
            biome = self.geography.biomes[y, x]
            stl = self._settlement_mgr.create_settlement(x, y, 0, biome)
            self.settlements[stl.id] = stl
            self.event_history_by_settlement[stl.id] = []
            self._last_ruler_change[stl.id] = 0
            self._pop_milestones[stl.id] = 500

            ruler = self._create_initial_ruler_and_heir(stl, 0)
            self._informant_mgr.ensure_settlement_roles(self, stl, 0)

            event = self._event_gen.generate_founding_event(
                stl.id, stl.name, 0, stl.ruler_name, ruler.id)
            self._add_event_with_evidence(event)

        # Step 3: 逐年模拟（分阶段）
        for year in range(1, years + 1):
            self.current_year = year
            self._tick_year(year, rng)

        self.current_year = years

    # ---- 年度模拟（Phase 2 分阶段） ----

    def _tick_year(self, year: int, rng: random.Random):
        """分阶段推进一年的模拟。"""
        alive = [s for s in self.settlements.values() if s.alive]

        # Phase A: 气候波动（内嵌在 tick_economy 中）
        # Phase B: 人口 + 经济
        for stl in self.settlements.values():
            if stl.alive:
                K = self._settlement_mgr.get_carrying_capacity(stl.biome)
                self._settlement_mgr.tick_population(stl, year, K)
                tick_economy(stl, self, rng)

        # Phase B2: notable-person mortality and political succession.
        self._tick_people(year)
        self._informant_mgr.ensure_all_roles(self, year)

        # Phase C: 计算压力
        self._pressures_cache = compute_all_pressures(self)

        # Phase D+E: 规则驱动事件评估 + 效果应用
        self._evaluate_rules_and_apply(year, alive, rng)

        # Phase F: 环境 pulse 事件（降低权重，仅非规则覆盖类型）
        self._ambient_pulse(year, alive, rng)

        # Phase G: 事件链处理
        self._process_event_chains(year, alive, rng)

        # Phase H: 证据衰减
        self._tick_evidence_decay(year, rng)

    def get_pressure(self, settlement_id: str, pressure_name: str) -> float:
        """获取某个聚落的某个压力指标值。"""
        return self._pressures_cache.get(settlement_id, {}).get(pressure_name, 0.0)

    # ---- Notable people and succession ----

    def _create_initial_ruler_and_heir(self, settlement: Settlement,
                                       year: int) -> Person:
        ruler_age = self._person_mgr.rng.randint(35, 55)
        ruler = self._person_mgr.create_person(
            settlement.id, year - ruler_age,
            roles=["founder", "ruler"], name=settlement.ruler_name)
        self.persons[ruler.id] = ruler
        settlement.ruler_id = ruler.id
        self._ensure_heir(ruler, year)
        return ruler

    def _create_notable_person(self, settlement_id: str, year: int,
                               role: str, min_age: int = 18,
                               max_age: int = 45,
                               name: str | None = None,
                               parent_ids: list[str] | None = None) -> Person:
        age = self._person_mgr.rng.randint(min_age, max_age)
        person = self._person_mgr.create_person(
            settlement_id, year - age, roles=[role], name=name,
            parent_ids=parent_ids)
        self.persons[person.id] = person
        return person

    def _ensure_heir(self, ruler: Person, year: int) -> Person:
        existing = [
            person for person in self.persons.values()
            if person.alive and person.settlement_id == ruler.settlement_id
            and "heir" in person.roles and person.id != ruler.id
        ]
        if existing:
            return sorted(existing, key=lambda person: person.id)[0]

        ruler_age = ruler.age_at(year)
        if ruler_age >= 30:
            max_age = max(12, min(25, ruler_age - 18))
            min_age = min(12, max_age)
            parent_ids = [ruler.id]
        else:
            min_age, max_age = 16, 35
            parent_ids = []
        return self._create_notable_person(
            ruler.settlement_id, year, "heir", min_age, max_age,
            parent_ids=parent_ids)

    def _get_or_create_officeholder(self, settlement_id: str, year: int,
                                    role: str) -> Person:
        candidates = [
            person for person in self.persons.values()
            if person.alive and person.settlement_id == settlement_id
            and role in person.roles
        ]
        if candidates:
            return sorted(candidates, key=lambda person: person.id)[0]
        return self._create_notable_person(settlement_id, year, role)

    def _tick_people(self, year: int) -> None:
        deaths = [
            person for person in self.persons.values()
            if person.alive and self._person_mgr.should_die(person, year)
        ]
        if not deaths:
            return

        for person in deaths:
            person.alive = False
            person.death_year = year

        for ruler in deaths:
            controlled = [
                settlement for settlement in self.settlements.values()
                if settlement.alive and settlement.ruler_id == ruler.id
            ]
            if not controlled:
                continue
            successor = self._select_successor(ruler, year)
            successor.add_role("ruler")
            successor.remove_role("heir")
            for settlement in controlled:
                self._apply_succession(settlement, ruler, successor, year)
            self._ensure_heir(successor, year)

    def _select_successor(self, ruler: Person, year: int) -> Person:
        living = [
            person for person in self.persons.values()
            if person.alive and person.id != ruler.id
            and person.settlement_id == ruler.settlement_id
        ]
        ranked = sorted(
            living,
            key=lambda person: (
                0 if "heir" in person.roles else 1,
                0 if ruler.id in person.parent_ids else 1,
                0 if person.id in ruler.spouse_ids else 1,
                -person.age_at(year),
                person.id,
            ),
        )
        if ranked:
            return ranked[0]
        return self._create_notable_person(
            ruler.settlement_id, year, "heir", 18, 40)

    def _apply_succession(self, settlement: Settlement, old_ruler: Person,
                          new_ruler: Person, year: int) -> None:
        effect = ChangeRuler(
            settlement.id, old_ruler.name, new_ruler.name,
            change_type="death", reason="succession")
        effect_ids = self._effect_resolver.apply_effects([effect], self)
        if not effect_ids:
            return
        settlement.ruler_id = new_ruler.id
        event = self._event_gen.generate_ruler_change_event(
            year, settlement.id, settlement.name,
            old_ruler.name, new_ruler.name, "death",
            old_ruler.id, new_ruler.id)
        event.effect_ids = effect_ids
        event.effects = [effect_to_dict(effect)]
        event.importance_score = 0.4
        event.visibility_score = 0.8
        self._add_event_with_evidence(event)
        self._record_effect_sources(event, [effect])
        self._last_ruler_change[settlement.id] = year

    # ---- 规则驱动事件评估 ----

    def _evaluate_rules_and_apply(self, year: int, alive: list[Settlement],
                                   rng: random.Random):
        """
        遍历 EventRuleRegistry，对每个规则评估候选聚落。
        通过检查的规则：解析 effects、应用效果、生成事件、记录因果。
        """
        triggered_groups: dict[str, set[str]] = {}
        rules = self._rule_registry.get_rules_sorted()

        for rule in rules:
            # 全局规则（如战争）：只需评估一个 settlement 作为 anchor
            if rule.is_global:
                if not alive:
                    continue
                # 随机选一个作为"发起方"评估
                anchor = rng.choice(alive)
                result = rule.evaluate(self, anchor, rng, year)
                if result is None:
                    continue
                target_id = result.target_settlement_id or "none"
                cooldown_key = "|".join(sorted((anchor.id, target_id)))
                if self._is_on_cooldown(rule.event_type, cooldown_key, year):
                    continue
                self._apply_rule_result(result, year, anchor, rng)
                self._record_trigger(rule.event_type, cooldown_key, year)
                continue

            # 单聚落规则：遍历候选
            candidates = list(alive)
            # 为每个 settlement 独立评估（非全局规则）
            for stl in candidates:
                if not stl.alive:
                    continue
                # 检查互斥
                settlement_groups = triggered_groups.setdefault(stl.id, set())
                if any(g in settlement_groups for g in rule.mutual_exclusion_groups):
                    continue
                # 检查 cooldown
                if self._is_on_cooldown(rule.event_type, stl.id, year):
                    continue

                result = rule.evaluate(self, stl, rng, year)
                if result is None:
                    continue

                self._apply_rule_result(result, year, stl, rng)
                self._record_trigger(rule.event_type, stl.id, year)
                settlement_groups.update(rule.mutual_exclusion_groups)

    def _apply_rule_result(self, result: EventRuleResult, year: int,
                           stl: Settlement, rng: random.Random):
        """应用规则结果：执行 effects、生成 event、记录因果。"""
        prior_rulers = {
            settlement_id: self.settlements[settlement_id].ruler_id
            for settlement_id in filter(None, (
                stl.id, result.target_settlement_id))
            if settlement_id in self.settlements
        }
        # 在 Effect 改变统治者等状态前固定事件文本和参与者。
        event = self._build_event_from_rule_result(result, year, [], stl, rng)
        event.cause_event_ids = self._find_cause_events(
            stl.id, year, event.event_type, result.trigger_factors)
        if event.event_type == "disaster":
            event.process_id = f"disaster_aftermath:{event.id}"

        # 应用 effects
        effect_ids = self._effect_resolver.apply_effects(
            result.concrete_effects, self)
        if result.concrete_effects and not effect_ids:
            return
        event.effect_ids = effect_ids
        event.effects = [effect_to_dict(effect) for effect in result.concrete_effects]

        # importance 和 visibility
        event.importance_score = result.selected_outcome.severity
        event.visibility_score = 0.8 if result.selected_outcome.severity > 0.5 else 0.5
        self._attach_people_to_rule_event(
            event, result, stl, year, prior_rulers)

        # 调试输出
        if self.debug_causes:
            print(f"[{event.year}] {event.title} ({event.event_type}) "
                  f"score={result.total_score:.2f}")
            for factor, val in sorted(result.trigger_factors.items(), key=lambda x: -x[1]):
                print(f"    {factor}: {val:.3f}")

        # 添加事件和证据
        self._add_event_with_evidence(event)
        self._record_effect_sources(event, result.concrete_effects)

        # 对战争结果特殊处理：摧毁或 pending
        if event.event_type == "war":
            outcome = result.selected_outcome.outcome_type
            # 获取对手（从 participants 中取非 primary_location 的那个）
            opponent_id = None
            for pid in event.participants:
                if pid != event.primary_location:
                    opponent_id = pid
                    break
            if opponent_id:
                pair_str = f"{min(event.primary_location, opponent_id)}|{max(event.primary_location, opponent_id)}"
                self._recent_war_years[pair_str] = year
                if outcome == "defender_victory":
                    self._pending_war_settlements.append(
                        (opponent_id, year, event.primary_location))
                else:
                    self._pending_war_settlements.append(
                        (event.primary_location, year, opponent_id))
        elif event.event_type == "disaster" and stl.alive:
            self._pending_disaster_aftermaths.append((
                stl.id,
                year,
                event.id,
                result.selected_outcome.outcome_type,
            ))
        if event.event_type == "literary_work":
            self._pending_literary_spreads.append((stl.id, year, event.id))

    def _attach_people_to_rule_event(self, event: HistoricalEvent,
                                     result: EventRuleResult,
                                     settlement: Settlement, year: int,
                                     prior_rulers: dict[str, str | None]) -> None:
        """Attach persistent people after a rule transaction succeeds."""
        if event.event_type == "war":
            commanders = []
            rulers = []
            for settlement_id in event.participants:
                commander = self._get_or_create_officeholder(
                    settlement_id, year, "general")
                commanders.append(commander)
                ruler_id = prior_rulers.get(settlement_id)
                ruler = self.persons.get(ruler_id)
                if ruler is not None:
                    rulers.append(ruler)

            event.person_ids = list(dict.fromkeys(
                [person.id for person in commanders + rulers]))
            event.details.update({
                "commander_ids": [person.id for person in commanders],
                "commander_names": [person.name for person in commanders],
                "ruler_ids": [person.id for person in rulers],
                "attacker": settlement.name,
                "defender": self.settlements[
                    result.target_settlement_id].name,
                "outcome": result.selected_outcome.outcome_type,
            })

            if (result.selected_outcome.outcome_type == "attacker_victory"
                    and result.target_settlement_id):
                target = self.settlements[result.target_settlement_id]
                previous_id = prior_rulers.get(target.id)
                target.ruler_id = settlement.ruler_id
                self._remove_ruler_role_if_landless(previous_id)

        elif event.event_type == "rebellion":
            old_ruler_id = prior_rulers.get(settlement.id)
            old_ruler = self.persons.get(old_ruler_id)
            leader = self._create_notable_person(
                settlement.id, year, "rebel_leader", 20, 55,
                name=result.new_ruler_name)
            event.person_ids = [
                person_id for person_id in (old_ruler_id, leader.id)
                if person_id
            ]
            event.details.update({
                "old_ruler_id": old_ruler_id,
                "rebel_leader_id": leader.id,
                "rebel_leader_name": leader.name,
            })
            if result.selected_outcome.outcome_type == "ruler_overthrown":
                leader.add_role("ruler")
                settlement.ruler_id = leader.id
                settlement.ruler_name = leader.name
                event.details["new_ruler_id"] = leader.id
                self._remove_ruler_role_if_landless(
                    old_ruler.id if old_ruler else None)
                for person in self.persons.values():
                    if (person.alive and person.settlement_id == settlement.id
                            and person.id != leader.id):
                        person.remove_role("heir")
                self._ensure_heir(leader, year)
                self._last_ruler_change[settlement.id] = year

        elif event.event_type == "literary_work":
            author = self._get_or_create_officeholder(
                settlement.id, year, "writer")
            genre = result.selected_outcome.outcome_type
            work_title = self._stable_event_choice(
                event.id, LITERARY_TITLES.get(genre, ["无题文稿"]))
            genre_names = {
                "epic": "长篇叙事诗",
                "drama": "剧作",
                "chronicle": "地方编年史",
                "lyric_cycle": "组诗",
            }
            genre_name = genre_names.get(genre, "文学作品")
            event.title = f"{author.name}完成《{work_title}》"
            event.person_ids = [author.id]
            event.process_id = f"literary_work:{event.id}"
            event.details.update({
                "author_id": author.id,
                "author_name": author.name,
                "genre": genre,
                "genre_name": genre_name,
                "work_title": work_title,
                "description_cn": (
                    f"{year}年，{author.name}在{settlement.name}完成"
                    f"{genre_name}《{work_title}》。抄写者很快制作了数份副本。"
                ),
            })

        elif event.event_type == "theoretical_work":
            scholar = self._get_or_create_officeholder(
                settlement.id, year, "scholar")
            field = result.selected_outcome.outcome_type
            treatise_title = self._stable_event_choice(
                event.id, THEORETICAL_TITLES.get(field, ["自然原理论"]))
            field_names = {
                "mechanics": "力学",
                "agronomy": "农学",
                "medicine": "医理",
                "astronomy": "天文学",
            }
            field_name = field_names.get(field, "自然哲学")
            event.title = f"{scholar.name}完成《{treatise_title}》"
            event.person_ids = [scholar.id]
            event.process_id = f"research:{event.id}"
            event.details.update({
                "author_id": scholar.id,
                "author_name": scholar.name,
                "theory_field": field,
                "theory_field_name": field_name,
                "work_title": treatise_title,
                "description_cn": (
                    f"{year}年，{scholar.name}在{settlement.name}完成"
                    f"{field_name}论著《{treatise_title}》。书中整理了定义、"
                    "观察记录、反例和可供验证的推论。"
                ),
            })

        elif event.event_type == "discovery":
            discoverer = self._get_or_create_officeholder(
                settlement.id, year, "scholar")
            technology_name = self._stable_event_choice(
                event.id, TECHNOLOGY_TITLES)
            event.title = f"{settlement.name}制成{technology_name}"
            event.person_ids = [discoverer.id]
            event.details.update({
                "discoverer_id": discoverer.id,
                "discoverer_name": discoverer.name,
                "discovery_name": technology_name,
                "description_cn": (
                    f"{year}年，{discoverer.name}与工匠在{settlement.name}"
                    f"完成了{technology_name}的第一批可重复试制。"
                ),
            })

    def _stable_event_choice(self, event_id: str, options: list[str]) -> str:
        payload = f"{self.seed}|{event_id}".encode("utf-8")
        index = int(hashlib.sha256(payload).hexdigest()[:8], 16)
        return options[index % len(options)]

    def _remove_ruler_role_if_landless(self, person_id: str | None) -> None:
        if not person_id:
            return
        if any(settlement.alive and settlement.ruler_id == person_id
               for settlement in self.settlements.values()):
            return
        person = self.persons.get(person_id)
        if person is not None:
            person.remove_role("ruler")

    def _build_event_from_rule_result(self, result: EventRuleResult, year: int,
                                       effect_ids: list[str], stl: Settlement,
                                       rng: random.Random) -> HistoricalEvent:
        """用规则评估结果构建 HistoricalEvent。"""
        outcome = result.selected_outcome

        # 把模板中的占位符替换掉
        title = outcome.title_template_cn
        title = title.replace("$SETTLEMENT_NAME", stl.name)
        title = title.replace("$OLD_RULER", stl.ruler_name)
        opponent_name = _resolve_target_name(result, self)
        title = title.replace("$TARGET_NAME", opponent_name)
        title = title.replace("$PARTNER", opponent_name)

        desc = outcome.description_template_cn
        desc = desc.replace("$SETTLEMENT_NAME", stl.name)
        desc = desc.replace("$OLD_RULER", stl.ruler_name)
        desc = desc.replace("$TARGET_NAME", opponent_name)
        desc = desc.replace("$NEW_RULER", result.new_ruler_name or stl.ruler_name)
        desc = desc.replace("$PARTNER", opponent_name)

        # 如果没有 description template，使用 EventGenerator 生成
        if not desc:
            desc = f"{year}年，{title}。"

        # 确定参与者
        participants = [stl.id]
        if result.target_settlement_id:
            participants.append(result.target_settlement_id)

        event_id = self._event_gen._next_id()
        details = {
            "outcome_type": outcome.outcome_type,
            "description_cn": desc,
        }
        if result.rule.event_type == "construction":
            details["building_type"] = outcome.outcome_type
        elif result.rule.event_type == "economic":
            details["economic_type"] = outcome.outcome_type

        return HistoricalEvent(
            id=event_id,
            year=year,
            event_type=result.rule.event_type,
            title=title,
            severity=outcome.severity,
            primary_location=stl.id,
            participants=participants,
            details=details,
            effect_ids=effect_ids,
            effects=[effect_to_dict(effect) for effect in result.concrete_effects],
            trigger_factors=dict(result.trigger_factors),
            cause_event_ids=[],
            importance_score=outcome.severity,
            visibility_score=0.8 if outcome.severity > 0.5 else 0.5,
        )

    def _is_on_cooldown(self, event_type: str, settlement_id: str, year: int) -> bool:
        """检查事件类型对某聚落是否在冷却期内。"""
        if event_type not in self._rule_cooldowns:
            return False
        last = self._rule_cooldowns[event_type].get(settlement_id, -999)
        rule = self._rule_registry.rules.get(event_type)
        if rule is None:
            return False
        return year - last < rule.cooldown_years

    def _record_trigger(self, event_type: str, settlement_id: str, year: int):
        """记录事件触发时间。"""
        if event_type not in self._rule_cooldowns:
            self._rule_cooldowns[event_type] = {}
        self._rule_cooldowns[event_type][settlement_id] = year

    # ---- 环境 pulse（降低权重的旧事件类型） ----

    def _ambient_pulse(self, year: int, alive: list[Settlement], rng: random.Random):
        """
        保留非规则覆盖的轻量事件，概率降低到原来的 0.3。
        规则已覆盖: rebellion, economic, disaster, construction, trade, war, discovery
        仍在此处: festival, crime, exploration, omen, notable_birth, duel, marriage, ruler_change
        """
        REDUCTION = 0.3

        for stl in alive:
            if not stl.alive:
                continue
            pop_factor = min(stl.population / 1000.0, 1.5)

            # 节日
            culture_multiplier = 1.0 + min(
                stl.cultural_influence / 2.0, 1.0)
            if rng.random() < 0.25 * pop_factor * REDUCTION * culture_multiplier:
                event = self._event_gen.generate_festival_event(year, stl.id, stl.name)
                event.cause_event_ids = self._find_cause_events(
                    stl.id, year, "festival", {
                        "cultural_momentum": min(
                            stl.cultural_influence / 3.0, 1.0),
                    })
                self._add_event_with_evidence(event)

            # 犯罪
            if rng.random() < 0.08 * pop_factor * REDUCTION:
                event = self._event_gen.generate_crime_event(year, stl.id, stl.name)
                self._add_event_with_evidence(event)

            # 探险
            if rng.random() < 0.05 * pop_factor * REDUCTION:
                explorer = self._get_or_create_officeholder(
                    stl.id, year, "explorer")
                event = self._event_gen.generate_exploration_event(
                    year, stl.id, stl.name, explorer.name, explorer.id)
                self._add_event_with_evidence(event)

            # 天象
            if rng.random() < 0.06 * REDUCTION:
                event = self._event_gen.generate_omen_event(year, stl.id, stl.name)
                self._add_event_with_evidence(event)

            # 名人出生
            if rng.random() < 0.06 * pop_factor * REDUCTION:
                ruler = self.persons.get(stl.ruler_id)
                parent = (ruler if ruler is not None and ruler.alive
                          and rng.random() < 0.3 else
                          self._get_or_create_officeholder(
                              stl.id, year, "notable"))
                child = self._person_mgr.create_person(
                    stl.id, year, roles=["notable_child"],
                    parent_ids=[parent.id])
                self.persons[child.id] = child
                event = self._event_gen.generate_notable_birth(
                    year, stl.id, stl.name, child.name, parent.name,
                    child.id, parent.id)
                self._add_event_with_evidence(event)

            # 决斗
            if rng.random() < 0.03 * pop_factor * REDUCTION:
                a = self._get_or_create_officeholder(stl.id, year, "duelist")
                b = self._create_notable_person(stl.id, year, "duelist")
                cause = rng.choice(["荣誉之争", "土地纠纷", "情仇", "酒后争执"])
                event = self._event_gen.generate_duel_event(
                    year, stl.id, stl.name, a.name, b.name, cause,
                    a.id, b.id)
                self._add_event_with_evidence(event)

            # 政治联姻
            if rng.random() < 0.04 * pop_factor * REDUCTION:
                ruler = self.persons.get(stl.ruler_id)
                a = (ruler if ruler is not None and ruler.alive
                     and rng.random() < 0.5 else
                     self._get_or_create_officeholder(
                         stl.id, year, "noble"))
                b = self._create_notable_person(stl.id, year, "noble")
                a.spouse_ids.append(b.id)
                b.spouse_ids.append(a.id)
                event = self._event_gen.generate_marriage_event(
                    year, stl.id, stl.name, a.name, b.name, "political",
                    a.id, b.id)
                self._add_event_with_evidence(event)

            # 人口里程碑
            self._check_population_milestone(stl, year)

    # ---- 因果链 ----

    def _find_cause_events(self, settlement_id: str, year: int,
                            event_type: str,
                            trigger_factors: dict[str, float]) -> list[str]:
        """从造成当前压力的状态变更事件中提取直接原因。"""
        if event_type == "disaster":
            return []

        factor_dimensions = {
            "famine_pressure": (("food", -1),),
            "food_stock_low": (("food", -1),),
            "food_stock_high": (("food", 1),),
            "unrest_pressure": (
                ("food", -1), ("stability", -1), ("legitimacy", -1)),
            "legitimacy_inverse": (("legitimacy", -1), ("ruler", 0)),
            "legitimacy_factor": (("legitimacy", 1), ("ruler", 0)),
            "stability_inverse": (("stability", -1),),
            "treasury_low": (("treasury", -1),),
            "treasury_high": (("treasury", 1),),
            "treasury_factor": (("treasury", 1),),
            "trade_pressure": (("food", -1), ("treasury", -1)),
            "expansion_pressure": (
                ("population", 1), ("food", 1), ("treasury", 1)),
            "avg_hostility": (("hostility", 1),),
            "trust_avg": (("trust", 1),),
            "invasion_risk": (("hostility", 1), ("stability", -1)),
            "population_factor": (("population", 1),),
            "library_factor": (("infrastructure", 1),),
            "cultural_momentum": (("culture", 1),),
            "theoretical_knowledge": (("theory", 1),),
        }

        sources = self._state_cause_sources.get(settlement_id, {})
        candidates: list[tuple[int, str]] = []
        seen: set[str] = set()
        for factor, value in sorted(
                trigger_factors.items(), key=lambda item: item[1], reverse=True):
            if value < 0.25:
                continue
            for dimension, required_direction in factor_dimensions.get(factor, ()):
                source = sources.get(dimension)
                if isinstance(source, str):
                    source = {"event_id": source, "direction": 0}
                if not source:
                    continue
                event_id = source.get("event_id")
                direction = source.get("direction", 0)
                if required_direction and direction != required_direction:
                    continue
                if not event_id or event_id in seen:
                    continue
                source_event = self.get_event(event_id)
                if source_event is None or not (0 < year - source_event.year <= 15):
                    continue
                candidates.append((source_event.year, event_id))
                seen.add(event_id)

        candidates.sort(reverse=True)
        return [event_id for _, event_id in candidates[:3]]

    def _record_effect_sources(self, event: HistoricalEvent, effects: list) -> None:
        """记录哪些事件最近改变了哪些状态维度。"""
        def direction(value: float) -> int:
            return 1 if value > 0 else -1 if value < 0 else 0

        def record(settlement_id: str, dimension: str, change_direction: int):
            if settlement_id not in self.settlements:
                return
            if change_direction == 0:
                return
            self._state_cause_sources.setdefault(settlement_id, {})[dimension] = {
                "event_id": event.id,
                "direction": change_direction,
            }

        for effect in effects:
            if isinstance(effect, ModifyPopulation):
                record(effect.settlement_id, "population",
                       direction(effect.delta + effect.percent))
            elif isinstance(effect, ModifyFoodStock):
                record(effect.settlement_id, "food",
                       direction(effect.delta + effect.percent))
            elif isinstance(effect, ModifyTreasury):
                record(effect.settlement_id, "treasury",
                       direction(effect.delta + effect.percent))
            elif isinstance(effect, ModifyStability):
                record(effect.settlement_id, "stability", direction(effect.delta))
            elif isinstance(effect, ModifyLegitimacy):
                record(effect.settlement_id, "legitimacy", direction(effect.delta))
            elif isinstance(effect, ModifyCulturalInfluence):
                record(effect.settlement_id, "culture", direction(effect.delta))
            elif isinstance(effect, ModifyTheoreticalKnowledge):
                record(effect.settlement_id, "theory", direction(effect.delta))
            elif isinstance(effect, ModifyTechnologyLevel):
                record(effect.settlement_id, "technology", direction(effect.delta))
            elif isinstance(effect, ModifyRelationship):
                trust_direction = direction(effect.trust_delta)
                hostility_direction = direction(effect.hostility_delta)
                record(effect.settlement_a, "trust", trust_direction)
                record(effect.settlement_b, "trust", trust_direction)
                record(effect.settlement_a, "hostility", hostility_direction)
                record(effect.settlement_b, "hostility", hostility_direction)
            elif isinstance(effect, (TransferControl, ChangeRuler)):
                record(effect.settlement_id, "ruler", 1)
            elif isinstance(effect, (DamageBuilding, ModifyInfrastructure)):
                change = -1 if isinstance(effect, DamageBuilding) else direction(effect.delta)
                record(effect.settlement_id, "infrastructure", change)
            elif isinstance(effect, DestroySettlement):
                record(effect.settlement_id, "population", -1)
                record(effect.settlement_id, "stability", -1)

    def build_causal_graph(self) -> nx.DiGraph:
        """构建所有事件的因果图。"""
        G = nx.DiGraph()
        for event in self.events:
            G.add_node(event.id, year=event.year, type=event.event_type,
                        title=event.title, importance=event.importance_score)
            for cause_id in event.cause_event_ids:
                if G.has_node(cause_id):
                    G.add_edge(cause_id, event.id)
        return G

    def print_event_causes(self, event_id: str, indent: int = 0) -> str:
        """递归打印事件的因果链（调试用）。"""
        event = self.get_event(event_id)
        if event is None:
            return f"Event {event_id} not found"

        lines = [f"{'  ' * indent}[{event.year}] {event.title}"]
        for cause_id in event.cause_event_ids:
            lines.append(self.print_event_causes(cause_id, indent + 1))
        return "\n".join(lines)

    def _process_event_chains(self, year: int, alive: list[Settlement], rng: random.Random):
        """处理前序事件引发的连锁事件。"""
        # 处理战争后续
        remaining = []
        for winner_id, war_year, loser_id in self._pending_war_settlements:
            years_after = year - war_year
            if years_after <= 0:
                remaining.append((winner_id, war_year, loser_id))
                continue

            winner = self.settlements.get(winner_id)
            loser = self.settlements.get(loser_id)
            war_event_id = next((
                event.id for event in reversed(self.events)
                if event.event_type == "war" and event.year == war_year
                and winner_id in event.participants and loser_id in event.participants
            ), None)

            # 战后 2~6 年：可能签订和约
            if 2 <= years_after <= 6 and rng.random() < 0.25:
                if winner and loser and loser.alive:
                    event = self._event_gen.generate_treaty_event(
                        year, winner.id, winner.name, loser.id, loser.name,
                        winner.id, "peace")
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._attach_current_rulers(event)
                    self._add_event_with_evidence(event)

            # 战后 1~3 年：可能发生报复袭击
            if 1 <= years_after <= 3 and rng.random() < 0.20:
                if winner and loser and loser.alive:
                    event = self._event_gen.generate_raid_event(
                        year, loser.id, loser.name, winner.id, winner.name, winner.id)
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._add_event_with_evidence(event)

            # 战后 5~15 年：可能结盟
            if 5 <= years_after <= 15 and rng.random() < 0.15:
                if winner and loser and loser.alive:
                    event = self._event_gen.generate_treaty_event(
                        year, winner.id, winner.name, loser.id, loser.name,
                        winner.id, "alliance")
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._attach_current_rulers(event)
                    self._add_event_with_evidence(event)

            # 保留 pending（最多 20 年）
            if years_after < 20:
                remaining.append((winner_id, war_year, loser_id))

        self._pending_war_settlements = remaining
        self._process_disaster_aftermaths(year)
        self._process_literary_spreads(year)

    def _attach_current_rulers(self, event: HistoricalEvent) -> None:
        signers = []
        used_ids = set()
        for settlement_id in event.participants:
            settlement = self.settlements.get(settlement_id)
            ruler = self.persons.get(settlement.ruler_id) if settlement else None
            signer = ruler if ruler is not None and ruler.alive else None
            if signer is not None and signer.id in used_ids:
                signer = self._get_or_create_officeholder(
                    settlement_id, event.year, "diplomat")
            if signer is not None:
                signers.append(signer)
                used_ids.add(signer.id)
        event.person_ids = [signer.id for signer in signers]
        event.details["signer_ids"] = [signer.id for signer in signers]
        event.details["signer_names"] = [signer.name for signer in signers]

    def _process_literary_spreads(self, year: int) -> None:
        remaining = []
        for source_id, work_year, work_event_id in self._pending_literary_spreads:
            years_after = year - work_year
            if years_after < 3:
                remaining.append((source_id, work_year, work_event_id))
                continue

            source = self.settlements.get(source_id)
            work_event = self.get_event(work_event_id)
            if source is None or not source.alive or work_event is None:
                continue
            partners = []
            for partner_id, relationship in source.relationships.items():
                partner = self.settlements.get(partner_id)
                if partner is None or not partner.alive:
                    continue
                if relationship.trust < 0.55 and relationship.trade_volume <= 0:
                    continue
                partners.append((
                    relationship.trust,
                    relationship.trade_volume,
                    partner.id,
                    partner,
                ))
            if not partners:
                continue
            partners.sort(key=lambda item: (-item[0], -item[1], item[2]))
            target = partners[0][3]
            scribe = self._get_or_create_officeholder(
                target.id, year, "scribe")
            event = self._event_gen.generate_literary_spread_event(
                year, source.id, source.name, target.id, target.name,
                work_event.details["work_title"],
                work_event.details["author_name"])
            event.person_ids = [scribe.id]
            event.details.update({
                "scribe_id": scribe.id,
                "scribe_name": scribe.name,
                "genre": work_event.details.get("genre", "epic"),
                "genre_name": work_event.details.get(
                    "genre_name", "文学作品"),
            })
            event.cause_event_ids = [work_event_id]
            event.process_id = work_event.process_id
            effects = [
                ModifyTreasury(target.id, delta=-10.0,
                               reason="copy_literary_work"),
                ModifyCulturalInfluence(target.id, delta=0.18,
                                        reason="literary_spread"),
                ModifyRelationship(source.id, target.id, trust_delta=0.03,
                                   reason="shared_literature"),
            ]
            self._apply_chained_event(event, effects)

        self._pending_literary_spreads = remaining

    def _process_disaster_aftermaths(self, year: int):
        """Resolve each non-terminal disaster into one state-dependent aftermath."""
        remaining = []
        for settlement_id, disaster_year, disaster_id, disaster_type in \
                self._pending_disaster_aftermaths:
            years_after = year - disaster_year
            if years_after < 2:
                remaining.append(
                    (settlement_id, disaster_year, disaster_id, disaster_type))
                continue

            settlement = self.settlements.get(settlement_id)
            disaster = self.get_event(disaster_id)
            if settlement is None or not settlement.alive or disaster is None:
                continue

            building_type, building_name = DISASTER_RECOVERY_FOCUS.get(
                disaster_type, ("market", "公共设施"))
            # Reconstruction represents several years of public works, not a
            # single annual maintenance payment.
            recovery_cost = (
                400.0 + settlement.population * 12.0 + disaster.severity * 700.0)
            donor = self._best_relief_donor(settlement)

            if settlement.treasury >= recovery_cost:
                expense = min(settlement.treasury, max(100.0, recovery_cost * 0.45))
                event = self._event_gen.generate_reconstruction_event(
                    year, settlement.id, settlement.name,
                    building_type, building_name)
                effects = [
                    ModifyTreasury(settlement.id, delta=-expense,
                                   reason="disaster_reconstruction"),
                    ModifyInfrastructure(settlement.id, building_type, delta=0.5,
                                         reason="disaster_reconstruction"),
                    ModifyStability(settlement.id, delta=0.06,
                                    reason="visible_recovery"),
                    ModifyLegitimacy(settlement.id, delta=0.04,
                                     reason="effective_recovery"),
                ]
                event.trigger_factors = {
                    "recovery_cost": recovery_cost,
                    "available_treasury": settlement.treasury,
                }
            elif donor is not None:
                contribution = min(80.0, donor.treasury * 0.25)
                food_aid = min(
                    donor.food_stock * 0.25,
                    max(100.0, settlement.population * 2.0))
                event = self._event_gen.generate_relief_event(
                    year, settlement.id, settlement.name, donor.id, donor.name)
                effects = [
                    ModifyTreasury(donor.id, delta=-contribution,
                                   reason="disaster_relief"),
                    ModifyTreasury(settlement.id, delta=contribution,
                                   reason="disaster_relief"),
                    ModifyFoodStock(donor.id, delta=-food_aid,
                                    reason="disaster_relief"),
                    ModifyFoodStock(settlement.id, delta=food_aid,
                                    reason="disaster_relief"),
                    ModifyInfrastructure(settlement.id, building_type, delta=0.25,
                                         reason="relief_repairs"),
                    ModifyStability(settlement.id, delta=0.05,
                                    reason="relief_received"),
                    ModifyRelationship(settlement.id, donor.id, trust_delta=0.10,
                                       hostility_delta=-0.03,
                                       reason="disaster_relief"),
                ]
                event.trigger_factors = {
                    "recovery_cost": recovery_cost,
                    "available_treasury": settlement.treasury,
                    "donor_trust": settlement.relationships[donor.id].trust,
                }
            else:
                event = self._event_gen.generate_decline_event(
                    year, settlement.id, settlement.name)
                effects = [
                    ModifyPopulation(settlement.id, percent=-0.07,
                                     reason="post_disaster_migration"),
                    ModifyTreasury(settlement.id, percent=-0.15,
                                   reason="post_disaster_decline"),
                    ModifyStability(settlement.id, delta=-0.08,
                                    reason="post_disaster_decline"),
                    ModifyLegitimacy(settlement.id, delta=-0.06,
                                     reason="failed_recovery"),
                    DamageBuilding(settlement.id, building_type, 0.20,
                                   reason="deferred_repairs"),
                ]
                event.trigger_factors = {
                    "recovery_cost": recovery_cost,
                    "available_treasury": settlement.treasury,
                }

            event.cause_event_ids = [disaster_id]
            event.process_id = disaster.process_id
            self._apply_chained_event(event, effects)

        self._pending_disaster_aftermaths = remaining

    def _best_relief_donor(self, recipient: Settlement) -> Settlement | None:
        """Return the strongest eligible partner without reading hidden truth."""
        candidates = []
        for partner_id, relationship in recipient.relationships.items():
            partner = self.settlements.get(partner_id)
            if (partner is None or not partner.alive
                    or relationship.trust < 0.58
                    or partner.treasury < 100.0
                    or partner.food_stock < 100.0):
                continue
            candidates.append((
                relationship.trust,
                partner.treasury + partner.food_stock * 0.1,
                partner.id,
                partner,
            ))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        return candidates[0][3]

    def _apply_chained_event(self, event: HistoricalEvent, effects: list) -> bool:
        """Transactionally apply and persist a generated follow-up event."""
        effect_ids = self._effect_resolver.apply_effects(effects, self)
        if effects and not effect_ids:
            return False
        event.effect_ids = effect_ids
        event.effects = [effect_to_dict(effect) for effect in effects]
        self._add_event_with_evidence(event)
        self._record_effect_sources(event, effects)
        return True

    # ---- 辅助 ----

    def _check_population_milestone(self, stl: Settlement, year: int):
        """检查人口是否跨过里程碑。"""
        threshold = self._pop_milestones.get(stl.id, 500)
        if stl.population >= threshold:
            event = self._event_gen.generate_population_milestone(
                year, stl.id, stl.name, threshold)
            self._add_event_with_evidence(event)
            # 下一个里程碑
            next_milestones = [500, 1000, 2000, 3000, 5000]
            for m in next_milestones:
                if m > threshold:
                    self._pop_milestones[stl.id] = m
                    break
            else:
                self._pop_milestones[stl.id] = threshold + 1000

    def _add_event(self, event: HistoricalEvent):
        self.events.append(event)
        for participant_id in event.participants:
            if participant_id in self.event_history_by_settlement:
                self.event_history_by_settlement[participant_id].append(event.id)

    def _add_event_with_evidence(self, event: HistoricalEvent):
        """Add truth, perspective-bound records, and their physical carriers."""
        self._add_event(event)
        recipes = EVIDENCE_RECIPES.get(event.event_type, [])
        source_records = self._record_gen.create_records_for_event(
            event, recipes, self.settlements, self.persons)
        for record_versions in source_records.values():
            for record in record_versions:
                self.records[record.id] = record
        for evd in self._evidence_gen.create_evidence_for_event(
                event, source_records):
            self.evidence[evd.id] = evd
            settlement = self.settlements.get(evd.location_id)
            record = self.records.get(evd.source_record_id)
            if settlement is not None:
                self._storage_mgr.assign_evidence(
                    evd, settlement, evd.created_year,
                    owner_person_id=(record.author_person_id if record else None))
            self._informant_mgr.distribute_carrier(
                self, evd, record, event.year)

    # ---- 证据衰减 ----

    def _tick_evidence_decay(self, year: int, rng: random.Random):
        """对所有非销毁/非埋藏的证据施加一年自然衰减。"""
        decayed = 0
        for evd in self.evidence.values():
            if evd.state in ("destroyed", "buried"):
                continue
            # 获取气候因子
            climate = 1.0
            if evd.location_id in self.settlements:
                stl = self.settlements[evd.location_id]
                biome = stl.biome if stl.alive else self.geography.biomes[stl.grid_y][stl.grid_x]
                climate = get_climate_factor(biome)
            site = self.storage_sites.get(evd.container_id)
            if site is not None:
                climate *= site.effective_preservation_modifier
            destroyed = tick_natural_decay(evd, climate, rng)
            if destroyed:
                decayed += 1
        return decayed

    def _destroy_settlement(self, stl: Settlement, year: int, cause: str):
        """摧毁聚落，同时触发证据批量损毁和埋藏。"""
        rng = random.Random(self.seed + year * 13)
        self._settlement_mgr.destroy_settlement(stl, year, cause)

        # 战争洗劫 → 批量摧毁证据
        if cause == "war":
            apply_event_destruction(stl.id, self.evidence, "war_sack", rng)
        elif cause == "fire":
            apply_event_destruction(stl.id, self.evidence, "fire", rng)
        elif cause == "earthquake":
            apply_event_destruction(stl.id, self.evidence, "earthquake", rng)
            apply_burial_preservation(stl.id, self.evidence, rng)
        elif cause == "flood":
            apply_event_destruction(stl.id, self.evidence, "flood", rng)
        self._storage_mgr.destroy_settlement(
            stl, year, cause, self.evidence)

    def move_evidence(self, evidence_id: str, storage_site_id: str,
                      year: Optional[int] = None,
                      reason: str = "collection_transfer") -> bool:
        """Move one carrier and preserve an observable custody trail."""
        evidence = self.evidence.get(evidence_id)
        site = self.storage_sites.get(storage_site_id)
        if evidence is None or site is None or not site.alive:
            return False
        self._storage_mgr.move_evidence(
            evidence, site, self.current_year if year is None else year, reason)
        return True

    def _snapshot_storage(self, settlement_id: str) -> dict:
        return {
            "sites": {
                site_id: site.to_dict()
                for site_id, site in self.storage_sites.items()
            },
            "evidence": {
                evidence.id: {
                    "location_id": evidence.location_id,
                    "container_id": evidence.container_id,
                    "holder_type": evidence.holder_type,
                    "holder_id": evidence.holder_id,
                    "storage_position": evidence.storage_position,
                    "accessibility": evidence.accessibility,
                    "location_history": [
                        dict(item) for item in evidence.location_history],
                }
                for evidence in self.evidence.values()
                if evidence.location_id == settlement_id
            },
        }

    def _restore_storage_snapshot(self, snapshot: dict) -> None:
        self.storage_sites = {
            site_id: StorageSite.from_dict(site_data)
            for site_id, site_data in snapshot.get("sites", {}).items()
        }
        self._storage_mgr = StorageManager(self.seed, self.storage_sites)
        for evidence_id, state in snapshot.get("evidence", {}).items():
            evidence = self.evidence.get(evidence_id)
            if evidence is None:
                continue
            evidence.location_id = state["location_id"]
            evidence.container_id = state["container_id"]
            evidence.holder_type = state["holder_type"]
            evidence.holder_id = state["holder_id"]
            evidence.storage_position = state["storage_position"]
            evidence.accessibility = state["accessibility"]
            evidence.location_history = [
                dict(item) for item in state["location_history"]]

    # ---- 序列化 ----

    def to_dict(self) -> dict:
        """序列化世界状态（不含 Geography numpy 数组，可从 seed 重现）。"""
        return {
            "schema_version": 8,
            "seed": self.seed,
            "name": self.name,
            "current_year": self.current_year,
            "settlements": [s.to_dict() for s in self.settlements.values()],
            "events": [e.to_dict() for e in self.events],
            "evidence": [e.to_dict() for e in self.evidence.values()],
            "records": [record.to_dict() for record in self.records.values()],
            "persons": [person.to_dict() for person in self.persons.values()],
            "informants": [
                informant.to_dict() for informant in self.informants.values()],
            "knowledge_entries": [
                entry.to_dict() for entry in self.knowledge_entries.values()],
            "storage_sites": [
                site.to_dict() for site in self.storage_sites.values()],
            "event_history_by_settlement": {
                k: list(v) for k, v in self.event_history_by_settlement.items()
            },
            "_last_ruler_change": dict(self._last_ruler_change),
            "_pop_milestones": dict(self._pop_milestones),
            "_recent_war_years": dict(self._recent_war_years),
            "_pending_war_settlements": list(self._pending_war_settlements),
            "_pending_disaster_aftermaths": list(
                self._pending_disaster_aftermaths),
            "_pending_literary_spreads": list(
                self._pending_literary_spreads),
            "_rule_cooldowns": {
                event_type: dict(years)
                for event_type, years in self._rule_cooldowns.items()
            },
            "_state_cause_sources": {
                settlement_id: dict(sources)
                for settlement_id, sources in self._state_cause_sources.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "World":
        """从 dict 反序列化。Geography 需要外部重建（从 seed）。"""
        w = cls(seed=data["seed"], name=data.get("name", "Unknown World"))
        w.current_year = data.get("current_year", 0)
        w.settlements = {
            s_data["id"]: Settlement.from_dict(s_data)
            for s_data in data.get("settlements", [])
        }
        w.persons = {
            person_data["id"]: Person.from_dict(person_data)
            for person_data in data.get("persons", [])
        }
        w.informants = {
            item["id"]: Informant.from_dict(item)
            for item in data.get("informants", [])
        }
        w.knowledge_entries = {
            item["id"]: KnowledgeEntry.from_dict(item)
            for item in data.get("knowledge_entries", [])
        }
        w._informant_mgr = InformantManager(
            w.seed, w.informants, w.knowledge_entries)
        for settlement in w.settlements.values():
            if settlement.ruler_id in w.persons:
                continue
            legacy_id = f"person_legacy_{settlement.id}"
            ruler = Person(
                id=legacy_id,
                name=settlement.ruler_name or "Unknown Ruler",
                birth_year=w.current_year - 40,
                settlement_id=settlement.id,
                alive=settlement.alive,
                death_year=(None if settlement.alive
                            else settlement.destroyed_year),
                roles=["ruler"],
            )
            w.persons[legacy_id] = ruler
            settlement.ruler_id = legacy_id
        w.events = [HistoricalEvent.from_dict(e) for e in data.get("events", [])]
        w.evidence = {
            e_data["id"]: Evidence.from_dict(e_data)
            for e_data in data.get("evidence", [])
        }
        w.storage_sites = {
            site_data["id"]: StorageSite.from_dict(site_data)
            for site_data in data.get("storage_sites", [])
        }
        w._storage_mgr = StorageManager(w.seed, w.storage_sites)
        w.records = {
            record_data["id"]: HistoricalRecord.from_dict(record_data)
            for record_data in data.get("records", [])
        }
        w._record_gen = RecordGenerator(w.seed)
        if w.records:
            record_numbers = [
                int(record_id.rsplit("_", 1)[-1])
                for record_id in w.records
                if record_id.rsplit("_", 1)[-1].isdigit()
            ]
            w._record_gen.counter = max(record_numbers, default=0)
        else:
            # Saves predating schema 6 stored evidence but no record layer.
            for event in w.events:
                generated = w._record_gen.create_records_for_event(
                    event, EVIDENCE_RECIPES.get(event.event_type, []),
                    w.settlements, w.persons)
                for versions in generated.values():
                    for record in versions:
                        w.records[record.id] = record

        records_by_carrier: dict[tuple[str, str], list[HistoricalRecord]] = {}
        for record in w.records.values():
            if not record.source_event_ids:
                continue
            key = (record.source_event_ids[0], record.carrier_subtype)
            records_by_carrier.setdefault(key, []).append(record)
        for versions in records_by_carrier.values():
            versions.sort(key=lambda record: (
                record.copy_parent_id is not None,
                record.created_year,
                record.id,
            ))
        copy_offsets: dict[tuple[str, str], int] = {}
        for evidence in sorted(w.evidence.values(), key=lambda item: item.id):
            if evidence.source_record_id in w.records:
                continue
            base_subtype = (evidence.subtype.removesuffix("_copy")
                            if evidence.is_copy_of else evidence.subtype)
            versions = records_by_carrier.get(
                (evidence.event_id, base_subtype), [])
            if not versions:
                continue
            if evidence.is_copy_of:
                copies = [record for record in versions if record.copy_parent_id]
                offset_key = (evidence.event_id, base_subtype)
                offset = copy_offsets.get(offset_key, 0)
                record = copies[min(offset, len(copies) - 1)] if copies else versions[0]
                copy_offsets[offset_key] = offset + 1
            else:
                record = next(
                    (item for item in versions if item.copy_parent_id is None),
                    versions[0])
            evidence.source_record_id = record.id
            evidence.source_event_ids = [evidence.event_id]
            evidence.retained_claim_ids = [
                claim.id for claim in record.claimed_facts]
        # Saves created before evidence schema 4 did not persist document text.
        events_by_id = {event.id: event for event in w.events}
        for evidence in w.evidence.values():
            if (evidence.evidence_type == "document"
                    and "written_content" not in evidence.content_data):
                source_event = events_by_id.get(evidence.event_id)
                if source_event is not None:
                    parent = w.evidence.get(evidence.is_copy_of)
                    parent_written = (
                        parent.content_data.get("written_content")
                        if parent is not None else None)
                    if evidence.is_copy_of and parent_written:
                        evidence.content_data["written_content"] = \
                            build_written_copy_content(
                                parent_written, w.seed, evidence.id, 0,
                                evidence.created_year)
                    else:
                        evidence.content_data["written_content"] = \
                            build_written_content(
                                source_event, evidence.subtype, w.seed,
                                evidence.id,
                                is_copy=bool(evidence.is_copy_of))
                    evidence.schema_version = 4
        legacy_storage = "storage_sites" not in data
        for evidence in sorted(w.evidence.values(), key=lambda item: item.id):
            if (evidence.container_id in w.storage_sites
                    and evidence.holder_id in w.storage_sites):
                continue
            settlement = w.settlements.get(evidence.location_id)
            if settlement is None:
                continue
            record = w.records.get(evidence.source_record_id)
            w._storage_mgr.assign_evidence(
                evidence, settlement, evidence.created_year,
                owner_person_id=(record.author_person_id if record else None),
                reason="legacy_location_migration")
            evidence.schema_version = 6
        if legacy_storage:
            for settlement in w.settlements.values():
                if not settlement.alive:
                    w._storage_mgr.destroy_settlement(
                        settlement,
                        settlement.destroyed_year or w.current_year,
                        settlement.destruction_cause or "unknown",
                        w.evidence)
        w.event_history_by_settlement = {
            k: list(v) for k, v in data.get("event_history_by_settlement", {}).items()
        }
        w._last_ruler_change = dict(data.get("_last_ruler_change", {}))
        w._pop_milestones = dict(data.get("_pop_milestones", {}))
        w._recent_war_years = dict(data.get("_recent_war_years", {}))
        w._pending_war_settlements = list(data.get("_pending_war_settlements", []))
        w._pending_disaster_aftermaths = list(
            data.get("_pending_disaster_aftermaths", []))
        w._pending_literary_spreads = list(
            data.get("_pending_literary_spreads", []))
        w._rule_cooldowns = {
            event_type: dict(years)
            for event_type, years in data.get("_rule_cooldowns", {}).items()
        }
        w._state_cause_sources = {
            settlement_id: dict(sources)
            for settlement_id, sources in data.get("_state_cause_sources", {}).items()
        }
        if "informants" not in data:
            w._informant_mgr.ensure_all_roles(w, w.current_year)
            w._informant_mgr.rebuild_current_knowledge(w, w.current_year)
        return w

    # ---- 查询接口 ----

    def get_settlement_events(self, settlement_id: str) -> list[HistoricalEvent]:
        event_ids = self.event_history_by_settlement.get(settlement_id, [])
        return [e for e in self.events if e.id in event_ids]

    def get_evidence_at(self, location_id: str) -> list[Evidence]:
        return [e for e in self.evidence.values()
                if e.location_id == location_id and e.state != "destroyed"]

    def get_evidence_by_event(self, event_id: str) -> list[Evidence]:
        return [e for e in self.evidence.values() if e.event_id == event_id]

    def get_all_visible_evidence(self, location_id: str) -> list[Evidence]:
        return [e for e in self.get_evidence_at(location_id)
                if e.state in ("intact", "weathered", "ruined")
                and e.evidence_type != "oral"]

    def get_settlement(self, settlement_id: str) -> Optional[Settlement]:
        return self.settlements.get(settlement_id)

    def get_available_informants(
            self, settlement_id: str,
            roles: set[str] | None = None) -> list[Informant]:
        if self._informant_mgr is None:
            self._informant_mgr = InformantManager(
                self.seed, self.informants, self.knowledge_entries)
        return self._informant_mgr.active_informants(
            self, settlement_id, roles)

    def get_informant_knowledge(
            self, informant_id: str) -> list[KnowledgeEntry]:
        informant = self.informants.get(informant_id)
        if informant is None:
            return []
        return [
            self.knowledge_entries[entry_id]
            for entry_id in informant.known_entry_ids
            if entry_id in self.knowledge_entries
        ]

    def get_person(self, person_id: str) -> Optional[Person]:
        return self.persons.get(person_id)

    def get_event(self, event_id: str) -> Optional[HistoricalEvent]:
        for e in self.events:
            if e.id == event_id:
                return e
        return None

    def summary(self) -> str:
        alive = sum(1 for s in self.settlements.values() if s.alive)
        ruined = len(self.settlements) - alive
        return (
            f"=== {self.name} (seed={self.seed}) ===\n"
            f"年份: {self.current_year}\n"
            f"聚落: {len(self.settlements)} 个（现存 {alive}，废墟 {ruined}）\n"
            f"历史事件: {len(self.events)} 条\n"
            f"历史人物: {len(self.persons)} 人\n"
            f"证据: {len(self.evidence)} 件\n"
        )


# ---- 模块级辅助函数 ----

def _resolve_target_name(result, world):
    """解析 $TARGET_NAME 占位符——从 participants 中找对手。"""
    opponent_id = result.target_settlement_id
    if opponent_id:
        opponent = world.settlements.get(opponent_id)
        if opponent:
            return opponent.name
    return "邻国"
