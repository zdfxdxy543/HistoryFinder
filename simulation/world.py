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

from config import (
    DYNAMIC_FOUNDING_MAX_PER_YEAR,
    GRID_WIDTH, GRID_HEIGHT, SIM_YEARS, INITIAL_SETTLEMENT_COUNT,
)
from simulation.geography import Geography, pick_settlement_sites
from simulation.settlement import Settlement, SettlementManager
from simulation.polity import (
    Polity, PolityManager, SettlementControlPeriod,
)
from simulation.person import Person, PersonManager
from simulation.religion import (
    ReligionManager, ReligionTradition, primary_religion,
)
from simulation.informants import (
    Informant, InformantManager, KnowledgeEntry,
)
from simulation.events import HistoricalEvent, EventGenerator
from simulation.evidence import (
    EVIDENCE_RECIPES, RELIGIOUS_CONTENT_SUBTYPES, Evidence, EvidenceGenerator,
    tick_natural_decay, apply_event_destruction, apply_burial_preservation, get_climate_factor
)
from simulation.records import HistoricalRecord, RecordGenerator
from simulation.storage import StorageManager, StorageSite
from simulation.technology import TECHNOLOGY_CATALOG
from simulation.research import generate_research_process
from simulation.literary_generation import event_theme, role_theme
from simulation.mobility import (
    describe_person_movements,
    plan_disaster_population_displacement,
    plan_event_exchange_networks,
    plan_event_knowledge_transfers,
    plan_event_person_movements,
    plan_supplemental_event_transfers,
    plan_event_transfers,
)
from simulation.pressures import compute_all_pressures, tick_economy
from simulation.founding import (
    FoundingPlan,
    SettlementFoundingPlanner,
    build_founding_site_context,
)
from simulation.event_rules import EventRuleRegistry, EventRuleResult
from simulation.effects import (
    ChangeRuler,
    DamageBuilding,
    DestroySettlement,
    EffectResolver,
    FoundSettlement,
    ModifyFoodStock,
    ModifyInfrastructure,
    ModifyCulturalInfluence,
    ModifyReligiousPresence,
    ModifyReligiousTolerance,
    ModifyLegitimacy,
    ModifyPopulation,
    ModifyRelationship,
    ModifyStability,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
    ModifyTreasury,
    MovePerson,
    StrengthenExchangeNetwork,
    TransferControl,
    effect_to_dict,
)
from simulation.routes import (
    ROAD_OVERGROWN_YEARS,
    ROAD_RUINED_YEARS,
    ROUTE_ABANDONMENT_YEARS,
    TRADE_STALE_GRACE_YEARS,
    RoadSegment,
    RoutePlanner,
    TradeRoute,
    TravelGroup,
    caravan_id,
    road_segment_id,
    route_id,
    stable_route_int,
    traveler_id,
)
from simulation.signposts import SignBoard, Signpost
from simulation.historical_sites import (
    BurialRecord,
    HistoricalSite,
    HistoricalSiteManager,
)


DISASTER_RECOVERY_FOCUS = {
    "flood": ("market", "市场与排水沟"),
    "fire": ("market", "烧毁的公共建筑"),
    "drought": ("aqueduct", "引水设施"),
    "storm": ("market", "受损屋顶与市场"),
    "earthquake": ("fortification", "城墙和承重结构"),
}

LITERARY_TITLES = {
    # Legacy genres remain readable, but are no longer selected for new works.
    "epic": ["七座城门之歌", "灰河远征记", "守夜者长歌", "群山之后"],
    "drama": ["空王座", "两枚印记", "雨夜城门", "最后一盏灯"],
    "lyric_cycle": ["十二月歌", "井边短章", "风过麦田", "远路与归人"],
}

HISTORY_THEME_BY_EVENT = {
    "founding": "建城",
    "war": "战乱",
    "raid": "边境冲突",
    "rebellion": "反抗",
    "treaty": "盟约",
    "ruler_change": "继承",
    "disaster": "灾变",
    "relief": "救援",
    "reconstruction": "重建",
    "decline": "衰落",
    "discovery": "技术",
    "exploration": "远行",
    "construction": "营建",
    "trade": "商路",
    "economic": "生计",
    "population_milestone": "城镇发展",
}


BIOGRAPHY_THEME_BY_ROLE = {
    "founder": "建城",
    "ruler": "执政",
    "general": "征战",
    "rebel_leader": "反抗",
    "diplomat": "外交",
    "scholar": "研究",
    "writer": "写作",
    "heir": "继承",
}

THEORETICAL_TITLES = {
    "mechanics": ["重物、支点与绳索论", "轮轴比例考", "落体与斜面札论"],
    "agronomy": ["土性与轮作论", "谷种选择考", "水渠、坡地与收成"],
    "medicine": ["脉息与热病辨", "创伤清洗论", "草药配伍考"],
    "astronomy": ["行星周期表解", "影长与季节论", "星位观测法"],
}

WORLD_SCHEMA_VERSION = 18

@dataclass
class World:
    """世界容器。"""
    seed: int
    name: str = "Unknown World"
    current_year: int = 0

    geography: Optional[Geography] = None
    settlements: dict[str, Settlement] = field(default_factory=dict)
    polities: dict[str, Polity] = field(default_factory=dict)
    settlement_control_periods: dict[str, SettlementControlPeriod] = field(
        default_factory=dict)
    events: list[HistoricalEvent] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    records: dict[str, HistoricalRecord] = field(default_factory=dict)
    persons: dict[str, Person] = field(default_factory=dict)
    informants: dict[str, Informant] = field(default_factory=dict)
    knowledge_entries: dict[str, KnowledgeEntry] = field(default_factory=dict)
    storage_sites: dict[str, StorageSite] = field(default_factory=dict)
    trade_routes: dict[str, TradeRoute] = field(default_factory=dict)
    road_segments: dict[str, RoadSegment] = field(default_factory=dict)
    travel_groups: dict[str, TravelGroup] = field(default_factory=dict)
    signposts: dict[str, Signpost] = field(default_factory=dict)
    religions: dict[str, ReligionTradition] = field(default_factory=dict)
    historical_sites: dict[str, HistoricalSite] = field(default_factory=dict)
    burials: dict[str, BurialRecord] = field(default_factory=dict)
    event_history_by_settlement: dict[str, list[str]] = field(default_factory=dict)

    _settlement_mgr: Optional[SettlementManager] = None
    _polity_mgr: Optional[PolityManager] = None
    _event_gen: Optional[EventGenerator] = None
    _evidence_gen: Optional[EvidenceGenerator] = None
    _record_gen: Optional[RecordGenerator] = None
    _person_mgr: Optional[PersonManager] = None
    _informant_mgr: Optional[InformantManager] = None
    _storage_mgr: Optional[StorageManager] = None
    _founding_planner: Optional[SettlementFoundingPlanner] = None
    _religion_mgr: Optional[ReligionManager] = None
    _historical_site_mgr: Optional[HistoricalSiteManager] = None

    # 追踪状态
    _last_ruler_change: dict[str, int] = field(default_factory=dict)
    _pop_milestones: dict[str, int] = field(default_factory=dict)
    _recent_war_years: dict[str, int] = field(default_factory=dict)  # "a|b" -> last war year
    _pending_war_settlements: list[tuple[str, int, str]] = field(default_factory=list)
    _pending_disaster_aftermaths: list[tuple[str, int, str, str]] = field(
        default_factory=list)
    _pending_literary_spreads: list[tuple[str, int, str]] = field(
        default_factory=list)
    _last_founding_year: dict[str, int] = field(default_factory=dict)

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
        self._initialize_runtime_managers()
        self.geography = Geography(self.seed)

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

            tradition = self._religion_mgr.create_origin(stl, 0)
            stl.religious_presence[tradition.id] = 1.0
            stl.official_religion_id = tradition.id

            ruler = self._create_initial_ruler_and_heir(stl, 0)
            polity = self._polity_mgr.create_polity(stl.id, ruler.id, 0)
            self.polities[polity.id] = polity
            stl.controller_polity_id = polity.id
            control = self._polity_mgr.create_control_period(
                stl.id, polity.id, 0, "founding")
            self.settlement_control_periods[control.id] = control
            self._informant_mgr.ensure_settlement_roles(self, stl, 0)

            event = self._event_gen.generate_founding_event(
                stl.id, stl.name, 0, stl.ruler_name, ruler.id)
            control.event_id = event.id
            self._add_event_with_evidence(event)

        # Step 3: 逐年模拟（分阶段）
        for year in range(1, years + 1):
            self.current_year = year
            self._tick_year(year, rng)

        self.current_year = years
        self._sync_historical_sites()

    def _initialize_runtime_managers(self) -> None:
        self._settlement_mgr = SettlementManager(self.seed)
        self._polity_mgr = PolityManager(self.seed)
        self._event_gen = EventGenerator(self.seed)
        self._evidence_gen = EvidenceGenerator(self.seed)
        self._record_gen = RecordGenerator(self.seed)
        self._person_mgr = PersonManager(self.seed)
        self._informant_mgr = InformantManager(
            self.seed, self.informants, self.knowledge_entries)
        self._storage_mgr = StorageManager(self.seed, self.storage_sites)
        self._founding_planner = SettlementFoundingPlanner()
        self._religion_mgr = ReligionManager(self.seed, self.religions)
        self._historical_site_mgr = HistoricalSiteManager(
            self.seed, self.historical_sites, self.burials)
        self._rule_registry = EventRuleRegistry()
        self._effect_resolver = EffectResolver(self.seed)

    def get_settlement_at(self, x: int, y: int) -> Settlement | None:
        return next((
            settlement for settlement in self.settlements.values()
            if int(settlement.grid_x) == x and int(settlement.grid_y) == y
        ), None)

    def get_historical_sites_at(self, x: int, y: int) -> list[HistoricalSite]:
        return sorted((
            site for site in self.historical_sites.values()
            if (x, y) in site.occupied_cells
        ), key=lambda site: site.id)

    def get_burials_at_site(self, site_id: str) -> list[BurialRecord]:
        return sorted((
            burial for burial in self.burials.values()
            if burial.site_id == site_id
        ), key=lambda burial: (burial.burial_year, burial.id))

    def get_signposts_at(self, x: int, y: int) -> list[Signpost]:
        return sorted((
            signpost for signpost in self.signposts.values()
            if signpost.world_cell == (x, y)
        ), key=lambda signpost: signpost.id)

    def get_road_segments_at(self, x: int, y: int) -> list[RoadSegment]:
        cell = (x, y)
        return sorted((
            segment for segment in self.road_segments.values()
            if cell in {segment.cell_a, segment.cell_b}
        ), key=lambda segment: segment.id)

    def ensure_trade_route(self, settlement_a_id: str,
                           settlement_b_id: str,
                           event_id: str = "") -> TradeRoute | None:
        key = route_id(settlement_a_id, settlement_b_id)
        first = self.settlements.get(settlement_a_id)
        second = self.settlements.get(settlement_b_id)
        if (first is None or second is None or not first.alive or not second.alive
                or self.geography is None):
            return None
        existing = self.trade_routes.get(key)
        if existing is not None:
            if existing.status != "active":
                existing.status = "active"
                existing.closed_year = None
                existing.closure_reason = ""
                existing.last_active_year = self.current_year
                existing.revision += 1
                self._set_route_site_state(existing)
                for signpost in self.signposts.values():
                    if existing.id in signpost.route_ids:
                        signpost.abandoned_year = None
                        signpost.condition = "weathered"
                        signpost.revision += 1
            self._attach_route_segments(existing)
            self._ensure_route_signposts(existing)
            self._ensure_route_caravan(existing)
            self._ensure_route_travelers(existing)
            return existing
        path = RoutePlanner().plan(
            self,
            (int(first.grid_x), int(first.grid_y)),
            (int(second.grid_x), int(second.grid_y)),
        )
        if not path:
            return None
        route = TradeRoute(
            id=key,
            settlement_a_id=settlement_a_id,
            settlement_b_id=settlement_b_id,
            opened_year=self.current_year,
            opened_event_id=event_id,
            path=path,
        )
        self.trade_routes[key] = route
        self._attach_route_segments(route)
        self._ensure_route_signposts(route)
        self._ensure_route_caravan(route)
        self._ensure_route_travelers(route)
        return route

    def _attach_route_segments(self, route: TradeRoute) -> None:
        segment_ids = []
        for first, second in zip(route.path, route.path[1:]):
            segment_id = road_segment_id(first, second)
            segment = self.road_segments.get(segment_id)
            if segment is None:
                low, high = sorted((first, second))
                segment = RoadSegment(
                    id=segment_id,
                    cell_a=low,
                    cell_b=high,
                    built_year=route.opened_year,
                    last_used_year=route.last_active_year or route.opened_year,
                    status=("active" if route.status == "active"
                            else "disused"),
                    condition=1.0 if route.status == "active" else 0.55,
                )
                self.road_segments[segment_id] = segment
            segment.attach_route(
                route.id, self.current_year, active=route.status == "active")
            segment_ids.append(segment_id)
        if route.segment_ids != segment_ids:
            route.segment_ids = segment_ids
            route.revision += 1

    def _ensure_route_signposts(self, route: TradeRoute) -> None:
        if len(route.path) < 3:
            return
        selected = {1, len(route.path) - 2}
        selected.update(range(6, len(route.path) - 1, 6))
        other_route_cells = {
            cell for item in self.trade_routes.values()
            if item.id != route.id and item.status == "active"
            for cell in item.path
        }
        last_turn = -3
        for index in range(1, len(route.path) - 1):
            previous = route.path[index - 1]
            current = route.path[index]
            following = route.path[index + 1]
            before = (current[0] - previous[0], current[1] - previous[1])
            after = (following[0] - current[0], following[1] - current[1])
            if before != after and index - last_turn >= 3:
                selected.add(index)
                last_turn = index
            if current in other_route_cells:
                selected.add(index)

        first = self.settlements.get(route.settlement_a_id)
        second = self.settlements.get(route.settlement_b_id)
        if first is None or second is None:
            return
        for index in sorted(selected):
            cell = route.path[index]
            if self.get_settlement_at(*cell) is not None:
                continue
            signpost_id = f"signpost_{cell[0]}_{cell[1]}"
            builder = first if index <= len(route.path) // 2 else second
            boards = [
                SignBoard(
                    id=f"{signpost_id}_{route.id}_{first.id}",
                    destination_id=first.id,
                    displayed_name=first.name,
                    displayed_distance=str(index),
                    direction=self._route_direction(cell, route.path[index - 1]),
                    written_year=route.opened_year,
                    writer_person_id=builder.ruler_id or "",
                    source_route_id=route.id,
                ),
                SignBoard(
                    id=f"{signpost_id}_{route.id}_{second.id}",
                    destination_id=second.id,
                    displayed_name=second.name,
                    displayed_distance=str(len(route.path) - index - 1),
                    direction=self._route_direction(cell, route.path[index + 1]),
                    written_year=route.opened_year,
                    writer_person_id=builder.ruler_id or "",
                    source_route_id=route.id,
                ),
            ]
            signpost = self.signposts.get(signpost_id)
            if signpost is None:
                signpost = Signpost(
                    id=signpost_id,
                    world_cell=cell,
                    built_year=route.opened_year,
                    builder_settlement_id=builder.id,
                )
                self.signposts[signpost_id] = signpost
            signpost.add_boards(route.id, boards)

    @staticmethod
    def _route_direction(current: tuple[int, int],
                         target: tuple[int, int]) -> str:
        dx, dy = target[0] - current[0], target[1] - current[1]
        return {
            (0, -1): "north", (1, 0): "east",
            (0, 1): "south", (-1, 0): "west",
        }[(dx, dy)]

    def _ensure_route_caravan(self, route: TradeRoute) -> TravelGroup:
        if route.status != "active":
            raise ValueError(f"cannot create caravan for {route.status} route")
        key = caravan_id(route.id)
        existing = self.travel_groups.get(key)
        if existing is not None:
            return existing
        first = self.settlements[route.settlement_a_id]
        second = self.settlements[route.settlement_b_id]
        cargo_options = (
            "谷物与干粮", "织物与染料", "陶器与生活器具",
            "金属工具", "药草与香料", "书写材料",
        )
        cargo_seed = stable_route_int(str(self.seed), route.id, "cargo")
        cargo = [
            cargo_options[cargo_seed % len(cargo_options)],
            cargo_options[(cargo_seed // 7 + 2) % len(cargo_options)],
        ]
        initial_index = (
            stable_route_int(str(self.seed), route.id, "position")
            % max(1, len(route.path))
        )
        group = TravelGroup(
            id=key,
            route_id=route.id,
            origin_settlement_id=first.id,
            destination_settlement_id=second.id,
            path_index=initial_index,
            cargo=list(dict.fromkeys(cargo)),
            guard_count=1 + stable_route_int(
                str(self.seed), route.id, "guards") % 4,
        )
        self.travel_groups[key] = group
        return group

    def _ensure_route_travelers(self, route: TradeRoute) -> list[TravelGroup]:
        if route.status != "active":
            return []
        first = self.settlements[route.settlement_a_id]
        second = self.settlements[route.settlement_b_id]
        other_roles = ("traveler", "courier", "peddler")
        roles = (
            "pilgrim",
            other_roles[stable_route_int(
                str(self.seed), route.id, "traveler-role") % len(other_roles)],
        )
        result = []
        for index, role in enumerate(roles):
            key = traveler_id(route.id, index)
            existing = self.travel_groups.get(key)
            if existing is not None:
                result.append(existing)
                continue
            position_seed = stable_route_int(
                str(self.seed), route.id, "traveler-position", str(index))
            if len(route.path) > 2:
                initial_index = 1 + position_seed % (len(route.path) - 2)
            else:
                initial_index = position_seed % max(1, len(route.path))
            direction = 1 if position_seed % 2 == 0 else -1
            origin = first if direction > 0 else second
            destination = second if direction > 0 else first
            group = TravelGroup(
                id=key,
                route_id=route.id,
                origin_settlement_id=origin.id,
                destination_settlement_id=destination.id,
                path_index=initial_index,
                direction=direction,
                progress_minutes=stable_route_int(
                    str(self.seed), route.id, "traveler-progress", str(index)
                ) % 180,
                guard_count=0,
                group_type="traveler",
                traveler_role=role,
                dialogue_variant=stable_route_int(
                    str(self.seed), route.id, "traveler-dialogue", str(index)
                ) % 3,
            )
            self.travel_groups[key] = group
            result.append(group)
        return result

    def remove_trade_route(self, route_key: str,
                           preserve_signposts: bool = True) -> None:
        route = self.trade_routes.get(route_key)
        if route is None:
            return
        if preserve_signposts:
            self._abandon_trade_route(route, "trade_ended")
            return
        self.trade_routes.pop(route_key, None)
        for group_id in [
                item.id for item in self.travel_groups.values()
                if item.route_id == route_key]:
            self.travel_groups.pop(group_id, None)
        for segment_id in route.segment_ids:
            segment = self.road_segments.get(segment_id)
            if segment is None or route_key not in segment.route_ids:
                continue
            segment.route_ids.remove(route_key)
            if not segment.route_ids:
                self.road_segments.pop(segment_id, None)
            else:
                segment.revision += 1
        for signpost_id, signpost in list(self.signposts.items()):
            if route_key not in signpost.route_ids:
                continue
            if not preserve_signposts:
                signpost.route_ids.remove(route_key)
                signpost.original_boards = [
                    item for item in signpost.original_boards
                    if item.source_route_id != route_key]
                signpost.current_boards = [
                    item for item in signpost.current_boards
                    if item.source_route_id != route_key]
                if not signpost.route_ids:
                    self.signposts.pop(signpost_id, None)
                else:
                    signpost.revision += 1
                continue

    def _abandon_trade_route(self, route: TradeRoute, reason: str) -> None:
        if route.status == "abandoned":
            return
        route.status = "abandoned"
        route.closed_year = self.current_year
        route.closure_reason = reason
        route.revision += 1
        self._set_route_site_state(route)
        for group_id in [
                item.id for item in self.travel_groups.values()
                if item.route_id == route.id]:
            self.travel_groups.pop(group_id, None)
        for segment_id in route.segment_ids:
            segment = self.road_segments.get(segment_id)
            if segment is None:
                continue
            has_active_route = any(
                route_id in self.trade_routes
                and self.trade_routes[route_id].status == "active"
                for route_id in segment.route_ids)
            if not has_active_route and segment.status == "active":
                segment.status = "disused"
                segment.traffic_volume = 0.0
                segment.revision += 1
        for signpost in self.signposts.values():
            if route.id not in signpost.route_ids:
                continue
            has_active_route = any(
                route_id in self.trade_routes
                and self.trade_routes[route_id].status == "active"
                for route_id in signpost.route_ids)
            if not has_active_route:
                signpost.abandoned_year = self.current_year
                signpost.condition = "abandoned"
                signpost.revision += 1

    def _set_route_site_state(self, route: TradeRoute) -> None:
        for site in self.historical_sites.values():
            if site.route_id != route.id:
                continue
            expected = "active" if route.status == "active" else "abandoned"
            abandoned_year = None if route.status == "active" else route.closed_year
            if (site.state == expected
                    and site.abandoned_year == abandoned_year):
                continue
            site.state = expected
            site.abandoned_year = abandoned_year
            site.condition = 0.9 if route.status == "active" else 0.42
            site.revision += 1

    def _route_trade_volume(self, route: TradeRoute) -> float:
        first = self.settlements.get(route.settlement_a_id)
        second = self.settlements.get(route.settlement_b_id)
        if first is None or second is None:
            return 0.0
        values = []
        first_relationship = first.relationships.get(second.id)
        second_relationship = second.relationships.get(first.id)
        if first_relationship is not None:
            values.append(first_relationship.trade_volume)
        if second_relationship is not None:
            values.append(second_relationship.trade_volume)
        return sum(values) / len(values) if values else 0.0

    def _decay_stale_route_trade(self, route: TradeRoute, year: int) -> None:
        first = self.settlements.get(route.settlement_a_id)
        second = self.settlements.get(route.settlement_b_id)
        if first is None or second is None:
            return
        relationships = [
            relationship for relationship in (
                first.relationships.get(second.id),
                second.relationships.get(first.id),
            ) if relationship is not None
        ]
        if not relationships:
            return
        last_interaction = max(
            relationship.last_interaction_year
            for relationship in relationships)
        if year - last_interaction <= TRADE_STALE_GRACE_YEARS:
            return
        trust = sum(item.trust for item in relationships) / len(relationships)
        hostility = sum(
            item.hostility for item in relationships) / len(relationships)
        rate = 0.06 + hostility * 0.12 - trust * 0.03
        rate = max(0.025, min(0.2, rate))
        for relationship in relationships:
            if relationship.trade_volume <= 0.0:
                continue
            decay = max(1.0, relationship.trade_volume * rate)
            relationship.trade_volume = max(
                0.0, relationship.trade_volume - decay)

    def _tick_trade_routes(self, year: int) -> None:
        for route in sorted(self.trade_routes.values(), key=lambda item: item.id):
            if route.status != "active":
                continue
            first = self.settlements.get(route.settlement_a_id)
            second = self.settlements.get(route.settlement_b_id)
            if first is None or second is None or not first.alive or not second.alive:
                self._abandon_trade_route(route, "endpoint_destroyed")
                continue
            self._decay_stale_route_trade(route, year)
            volume = self._route_trade_volume(route)
            if volume > 0.0:
                route.last_active_year = year
            elif year - (route.last_active_year or route.opened_year) \
                    >= ROUTE_ABANDONMENT_YEARS:
                self._abandon_trade_route(route, "trade_inactive")

        for segment in self.road_segments.values():
            active_routes = [
                self.trade_routes[route_id]
                for route_id in segment.route_ids
                if route_id in self.trade_routes
                and self.trade_routes[route_id].status == "active"
            ]
            old_state = (segment.status, segment.condition,
                         segment.last_used_year, segment.traffic_volume)
            if active_routes:
                segment.status = "active"
                segment.last_used_year = year
                segment.traffic_volume = sum(
                    self._route_trade_volume(route) for route in active_routes)
                segment.condition = min(1.0, segment.condition + 0.04)
            else:
                unused_years = year - segment.last_used_year
                segment.traffic_volume = 0.0
                if unused_years >= ROAD_RUINED_YEARS:
                    segment.status = "ruined"
                    segment.condition = max(0.08, segment.condition - 0.08)
                elif unused_years >= ROAD_OVERGROWN_YEARS:
                    segment.status = "overgrown"
                    segment.condition = max(0.28, segment.condition - 0.04)
                else:
                    segment.status = "disused"
                    segment.condition = max(0.5, segment.condition - 0.02)
            if old_state != (segment.status, segment.condition,
                             segment.last_used_year, segment.traffic_volume):
                segment.revision += 1

    def repair_signpost(self, signpost_id: str, board_id: str,
                        repairer_person_id: str, event_id: str = "",
                        repair_type: str | None = None,
                        error_type: str | None = None):
        if repairer_person_id not in self.persons:
            raise ValueError(f"unknown signpost repairer: {repairer_person_id}")
        signpost = self.signposts[signpost_id]
        return signpost.repair(
            board_id, self.current_year, repairer_person_id, self.seed,
            event_id=event_id, repair_type=repair_type,
            error_type=error_type)

    def _tick_signposts(self, year: int) -> None:
        for signpost in self.signposts.values():
            signpost.weather_to(year, self.seed)

    def advance_travel_groups(self, minutes: int) -> None:
        for group in sorted(
                self.travel_groups.values(), key=lambda item: item.id):
            route = self.trade_routes.get(group.route_id)
            if route is not None:
                group.advance(minutes, route)

    def get_travel_groups_at(self, x: int, y: int) -> list[TravelGroup]:
        result = []
        for group in self.travel_groups.values():
            route = self.trade_routes.get(group.route_id)
            if route is not None and group.current_cell(route) == (x, y):
                result.append(group)
        return sorted(result, key=lambda item: item.id)

    def get_current_control_period(
            self, settlement_id: str) -> SettlementControlPeriod | None:
        current = [
            period for period in self.settlement_control_periods.values()
            if period.settlement_id == settlement_id
            and period.end_year is None
        ]
        if len(current) > 1:
            raise RuntimeError(
                f"multiple current control periods for {settlement_id}")
        return current[0] if current else None

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
        self._tick_person_mobility(year)
        self._tick_people(year)
        self._tick_religious_exchange(year)
        self._informant_mgr.ensure_all_roles(self, year)

        # Phase C: 计算压力
        self._pressures_cache = compute_all_pressures(self)

        # Phase C2: stable settlements may establish planned colonies.
        self._evaluate_natural_founding(year)

        # Phase D+E: 规则驱动事件评估 + 效果应用
        self._evaluate_rules_and_apply(year, alive, rng)

        # Phase F: 环境 pulse 事件（降低权重，仅非规则覆盖类型）
        self._ambient_pulse(year, alive, rng)

        # Phase G: 事件链处理
        self._process_event_chains(year, alive, rng)

        # Phase H: 证据衰减
        self._tick_evidence_decay(year, rng)
        self._tick_trade_routes(year)
        self._tick_signposts(year)

        # Event-linked travel can temporarily empty a local office after the
        # early-year staffing pass. Appoint an acting holder before year end.
        self._informant_mgr.ensure_all_roles(self, year)

    def get_pressure(self, settlement_id: str, pressure_name: str) -> float:
        """获取某个聚落的某个压力指标值。"""
        return self._pressures_cache.get(settlement_id, {}).get(pressure_name, 0.0)

    def _tick_religious_exchange(self, year: int) -> None:
        """Diffuse traditions gradually through established exchange ties."""
        snapshots = {
            settlement.id: dict(settlement.religious_presence)
            for settlement in self.settlements.values() if settlement.alive
        }
        additions: dict[tuple[str, str], float] = {}
        for target in sorted(
                self.settlements.values(), key=lambda item: item.id):
            if not target.alive:
                continue
            for source_id, relationship in sorted(target.relationships.items()):
                source = self.settlements.get(source_id)
                if source is None or not source.alive:
                    continue
                cultural = relationship.exchange_strengths.get("cultural", 0.0)
                trade = relationship.exchange_strengths.get("trade", 0.0)
                contact = cultural + trade * 0.35
                if contact < 0.20:
                    continue
                source_presence = snapshots.get(source.id, {})
                if not source_presence:
                    continue
                religion_id = max(
                    source_presence,
                    key=lambda key: (source_presence[key], key))
                if religion_id == target.official_religion_id:
                    continue
                current = snapshots.get(target.id, {}).get(religion_id, 0.0)
                if current >= 0.45:
                    continue
                cadence = int.from_bytes(hashlib.sha256(
                    f"religion-spread|{self.seed}|{target.id}|{source.id}|{year}"
                    .encode("utf-8")).digest()[:4], "big")
                if cadence % 3:
                    continue
                additions[(target.id, religion_id)] = min(
                    0.025, 0.004 + contact * 0.003)
        for (settlement_id, religion_id), delta in additions.items():
            settlement = self.settlements[settlement_id]
            settlement.religious_presence[religion_id] = min(
                1.0,
                settlement.religious_presence.get(religion_id, 0.0) + delta,
            )

    def _evaluate_natural_founding(self, year: int) -> list[str]:
        sources = [
            source for source in sorted(
                self.settlements.values(), key=lambda item: item.id)
            if self._founding_planner.may_attempt(self, source, year)
        ]
        if not sources:
            return []

        site_context = build_founding_site_context(self)
        plans = []
        for source in sources:
            plan = self._founding_planner.evaluate(
                self, source, year, site_context)
            if plan is not None:
                plans.append(plan)
        plans.sort(key=lambda plan: (
            -plan.trigger_factors.get("expansion_pressure", 0.0),
            -plan.site_factors.get("site_score", 0.0),
            plan.source_settlement_id,
        ))

        event_ids = []
        for plan in plans[:DYNAMIC_FOUNDING_MAX_PER_YEAR]:
            event = self._execute_founding_plan(plan, year)
            if event is not None:
                event_ids.append(event.id)
        return event_ids

    def _execute_founding_plan(
            self, plan: FoundingPlan,
            year: int) -> HistoricalEvent | None:
        source = self.settlements.get(plan.source_settlement_id)
        founder = self.persons.get(plan.founder_person_id)
        if source is None or founder is None:
            return None
        founder_was_heir = "heir" in founder.roles
        event_id = self._event_gen.reserve_id()
        effect = FoundSettlement(
            source_settlement_id=source.id,
            new_settlement_id=self._settlement_mgr.reserve_id(),
            new_settlement_name=self._settlement_mgr.reserve_name(),
            grid_x=plan.x,
            grid_y=plan.y,
            founded_year=year,
            biome=plan.biome,
            settler_count=plan.settler_count,
            food_transfer=plan.food_transfer,
            treasury_transfer=plan.treasury_transfer,
            founder_person_id=founder.id,
            controller_polity_id=plan.controller_polity_id,
            control_period_id=self._polity_mgr.reserve_control_id(),
            event_id=event_id,
            founding_type=plan.founding_type,
            reason=plan.founding_type,
        )
        effect_ids = self._effect_resolver.apply_effects([effect], self)
        if not effect_ids:
            return None

        settlement = self.settlements[effect.new_settlement_id]
        self._ensure_heir(founder, year)
        if founder_was_heir:
            source_ruler = self.persons.get(source.ruler_id)
            if source_ruler is not None and source_ruler.alive:
                self._ensure_heir(source_ruler, year)
        self._informant_mgr.ensure_settlement_roles(
            self, settlement, year)

        event = self._event_gen.generate_founding_event(
            settlement.id,
            settlement.name,
            year,
            founder.name,
            founder.id,
            origin_settlement_id=source.id,
            origin_settlement_name=source.name,
            settler_count=plan.settler_count,
            controller_polity_id=plan.controller_polity_id,
            founding_type=plan.founding_type,
            reserved_event_id=event_id,
        )
        event.effect_ids = effect_ids
        event.effects = [effect_to_dict(effect)]
        event.trigger_factors = {
            **plan.trigger_factors,
            **plan.site_factors,
        }
        event.cause_event_ids = self._find_cause_events(
            source.id, year, "founding", plan.trigger_factors)
        event.importance_score = 0.72
        event.visibility_score = 0.85
        self._add_event_with_evidence(event)
        self._record_effect_sources(event, [effect])
        self._last_founding_year[source.id] = year
        return event

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
            and person.current_location_id == settlement_id
            and role in person.roles
        ]
        if candidates:
            return sorted(candidates, key=lambda person: person.id)[0]
        return self._create_notable_person(settlement_id, year, role)

    def _tick_person_mobility(self, year: int) -> None:
        """Return temporary visitors, or strand them if home was destroyed."""
        returning = sorted((
            person for person in self.persons.values()
            if person.alive
            and person.mobility_status in {"visitor", "envoy"}
            and person.stay_until_year is not None
            and year > person.stay_until_year
        ), key=lambda person: person.id)
        for person in returning:
            home = self.settlements.get(person.settlement_id)
            if home is None or not home.alive:
                person.mobility_status = "displaced"
                person.travel_role = "refugee"
                person.stay_until_year = None
                person.carried_evidence_ids = []
                continue
            effect = MovePerson(
                person_id=person.id,
                target_settlement_id=home.id,
                movement_type="return_home",
                mobility_status="resident",
                travel_role="",
                stay_until_year=None,
            )
            self._effect_resolver.apply_effects([effect], self)

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

    def _sync_historical_sites(self) -> None:
        if self._historical_site_mgr is None:
            self._historical_site_mgr = HistoricalSiteManager(
                self.seed, self.historical_sites, self.burials)
        new_burials = self._historical_site_mgr.sync(self)
        for site in self.historical_sites.values():
            cell_id = f"{site.anchor_cell[0]},{site.anchor_cell[1]}"
            settlement = self.settlements.get(site.owner_settlement_id)
            settlement_cell = (
                (int(settlement.grid_x), int(settlement.grid_y))
                if settlement is not None else None)
            field_storage = (
                self._historical_site_storage(site, cell_id)
                if site.anchor_cell != settlement_cell else None)
            if site.site_type in {"cemetery", "abandoned_cemetery"}:
                continue
            for evidence in self.evidence.values():
                if (evidence.event_id not in site.source_event_ids
                        or evidence.location_type != "near_settlement"):
                    continue
                if field_storage is not None:
                    self._storage_mgr.move_evidence(
                        evidence, field_storage, self.current_year,
                        "historical_site_relocation",
                        event_id=(site.source_event_ids[-1]
                                  if site.source_event_ids else None),
                        transfer_type="site_relocation",
                    )
                evidence.location_type = "grid_cell"
                evidence.location_id = cell_id
                evidence.storage_position = "历史地点现场"
                if evidence.id not in site.evidence_ids:
                    site.evidence_ids.append(evidence.id)
                    site.revision += 1
            if field_storage is not None:
                self._ensure_historical_site_evidence(
                    site, field_storage, cell_id)
        for burial in new_burials:
            person = self.persons.get(burial.person_id)
            site = self.historical_sites.get(burial.site_id)
            settlement = (
                self.settlements.get(site.owner_settlement_id)
                if site is not None else None)
            if person is None or site is None or settlement is None:
                continue
            existing_tomb = next((
                evidence for evidence in self.evidence.values()
                if evidence.subtype == "ruler_tomb"
                and self.get_event(evidence.event_id) is not None
                and self.get_event(evidence.event_id).details.get(
                    "epitaph_subject_id") == person.id
            ), None)
            if existing_tomb is not None:
                burial.inscription_evidence_id = existing_tomb.id
                self._place_burial_marker(existing_tomb, site, settlement)
                if existing_tomb.id not in site.evidence_ids:
                    site.evidence_ids.append(existing_tomb.id)
                    site.revision += 1
                continue
            commissioner = self.persons.get(burial.commissioner_person_id)
            religion = self.religions.get(burial.religion_id)
            life_sources = [
                self._snapshot_history_event(event, person.id)
                for event_id in burial.source_event_ids
                if (event := self.get_event(event_id)) is not None
            ]
            event = self._event_gen.generate_burial_event(
                burial.burial_year, settlement.id, settlement.name,
                person, burial,
                commissioner.name if commissioner is not None else "",
                religion.text_profile() if religion is not None else {},
                life_sources,
            )
            self._add_event_with_evidence(event)
            marker = next((
                evidence for evidence in self.get_evidence_by_event(event.id)
                if evidence.subtype == "grave_marker"
            ), None)
            if marker is not None:
                climate = get_climate_factor(str(settlement.biome))
                elapsed = max(0, self.current_year - burial.burial_year)
                if site.state in {"abandoned", "ruined"}:
                    elapsed += 8
                for age_year in range(elapsed):
                    if marker.state == "destroyed":
                        break
                    tick_natural_decay(
                        marker, climate,
                        random.Random(
                            f"burial-decay|{self.seed}|{marker.id}|{age_year}"),
                    )
                burial.inscription_evidence_id = marker.id
                self._place_burial_marker(marker, site, settlement)
                marker.content_data["burial_id"] = burial.id
                marker.content_data["person_id"] = person.id
                if marker.id not in site.evidence_ids:
                    site.evidence_ids.append(marker.id)
                    site.revision += 1
        # Keep existing markers aligned if a previously empty cemetery was
        # assigned to a wilderness cell during this synchronization.
        for burial in self.burials.values():
            marker = self.evidence.get(burial.inscription_evidence_id)
            site = self.historical_sites.get(burial.site_id)
            settlement = (
                self.settlements.get(site.owner_settlement_id)
                if site is not None else None)
            if marker is not None and site is not None and settlement is not None:
                self._place_burial_marker(marker, site, settlement)

    def _historical_site_storage(
            self, site: HistoricalSite, cell_id: str) -> StorageSite:
        storage_id = f"storage_{site.id}"
        storage = self.storage_sites.get(storage_id)
        if storage is None:
            storage = StorageSite(
                id=storage_id,
                settlement_id=cell_id,
                site_type="field_site",
                name=f"{site.name}现场",
                accessibility="public",
                preservation_modifier=1.45,
                security=0.1,
                condition=site.condition,
                created_year=site.founded_year,
                alive=True,
            )
            self.storage_sites[storage.id] = storage
        else:
            storage.settlement_id = cell_id
            storage.name = f"{site.name}现场"
            storage.condition = site.condition
        return storage

    def _ensure_historical_site_evidence(
            self, site: HistoricalSite, storage: StorageSite,
            cell_id: str) -> None:
        remaining = max(0, 3 - len(site.evidence_ids))
        if remaining == 0:
            return
        existing_subtypes = {
            evidence.subtype
            for evidence_id in site.evidence_ids
            if (evidence := self.evidence.get(evidence_id)) is not None
        }
        candidates = []
        for event_id in site.source_event_ids:
            event = self.get_event(event_id)
            if event is None:
                continue
            recipes = [
                dict(recipe, copies=0)
                for recipe in EVIDENCE_RECIPES.get(event.event_type, [])
                if recipe["type"] != "oral"
                and recipe["subtype"] not in existing_subtypes
            ]
            recipes.sort(key=lambda recipe: (
                recipe["type"] == "document", recipe["subtype"]))
            for recipe in recipes:
                candidates.append((event, recipe))
                existing_subtypes.add(recipe["subtype"])
        for event, recipe in candidates[:remaining]:
            source_records = self._record_gen.create_records_for_event(
                event, [recipe], self.settlements, self.persons)
            for versions in source_records.values():
                for record in versions:
                    self.records[record.id] = record
            generated = self._evidence_gen.create_evidence_for_event(
                event, source_records, [recipe])
            if not generated:
                continue
            evidence = generated[0]
            evidence.content_data["historical_site_id"] = site.id
            evidence.location_type = "grid_cell"
            self.evidence[evidence.id] = evidence
            self._storage_mgr.move_evidence(
                evidence, storage, self.current_year,
                "historical_site_deposit",
                event_id=event.id,
                transfer_type="site_deposit",
            )
            evidence.location_id = cell_id
            if evidence.id not in site.evidence_ids:
                site.evidence_ids.append(evidence.id)
                site.revision += 1

    def _place_burial_marker(self, evidence: Evidence, site: HistoricalSite,
                             settlement: Settlement) -> None:
        settlement_cell = (
            int(settlement.grid_x), int(settlement.grid_y))
        if site.anchor_cell == settlement_cell:
            evidence.location_type = "settlement"
            evidence.location_id = settlement.id
            return
        evidence.location_type = "grid_cell"
        cell_id = f"{site.anchor_cell[0]},{site.anchor_cell[1]}"
        storage = self._historical_site_storage(site, cell_id)
        self._storage_mgr.move_evidence(
            evidence, storage, self.current_year,
            "burial_marker_placed",
            event_id=evidence.event_id,
            transfer_type="burial",
        )
        evidence.location_id = cell_id
        evidence.storage_position = "墓园原位置"

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
        polity = self.polities.get(settlement.controller_polity_id)
        if (polity is not None
                and polity.capital_settlement_id == settlement.id
                and polity.ruler_id == old_ruler.id):
            polity.ruler_id = new_ruler.id
        event = self._event_gen.generate_ruler_change_event(
            year, settlement.id, settlement.name,
            old_ruler.name, new_ruler.name, "death",
            old_ruler.id, new_ruler.id)
        life_sources = self._select_person_history(
            old_ruler.id, year, limit=6)
        event.details.update({
            "epitaph_subject_id": old_ruler.id,
            "epitaph_subject_name": old_ruler.name,
            "epitaph_location_name": settlement.name,
            "epitaph_birth_year": old_ruler.birth_year,
            "epitaph_death_year": year,
            "epitaph_age": old_ruler.age_at(year),
            "epitaph_roles": list(old_ruler.roles),
            "epitaph_sources": life_sources,
            "epitaph_source_event_ids": [
                source["event_id"] for source in life_sources
            ],
        })
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

        # Cross-settlement transfers are planned against the pre-event state
        # and participate in the same transaction as the event's other effects.
        transfer_effects = plan_event_transfers(self, event, result)
        concrete_effects = transfer_effects + result.concrete_effects

        # 应用 effects
        effect_ids = self._effect_resolver.apply_effects(
            concrete_effects, self)
        if concrete_effects and not effect_ids:
            return
        event.effect_ids = effect_ids
        event.effects = [effect_to_dict(effect) for effect in concrete_effects]

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
        self._record_effect_sources(event, concrete_effects)

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
            biography_subject = None
            if genre == "biography":
                biography_subject, literary_sources = \
                    self._select_biography_subject(
                        settlement.id, year, author.id)
                if biography_subject is None:
                    # A new world normally has at least its founder's history.
                    # Keep the event grounded if a minimal/legacy world does not.
                    genre = "chronicle"
                    literary_sources = self._select_literary_sources(
                        settlement.id, year)
            else:
                literary_sources = self._select_literary_sources(
                    settlement.id, year)
            work_title = self._build_literary_title(
                event.id, year, genre, settlement, literary_sources,
                biography_subject)
            genre_names = {
                "epic": "长篇叙事诗",
                "drama": "剧作",
                "chronicle": "地方编年史",
                "lyric_cycle": "组诗",
                "biography": "人物传记",
            }
            genre_name = genre_names.get(genre, "文学作品")
            event.title = f"{author.name}完成《{work_title}》"
            event.person_ids = [author.id]
            event.process_id = f"literary_work:{event.id}"
            event.details.update({
                "author_id": author.id,
                "author_name": author.name,
                "author_roles": list(author.roles),
                "genre": genre,
                "genre_name": genre_name,
                "work_title": work_title,
                "setting_name": settlement.name,
                "source_event_ids": [
                    source["event_id"] for source in literary_sources
                ],
                "literary_sources": literary_sources,
                "landscape_features": [
                    {
                        "id": feature.id,
                        "name": feature.name,
                        "feature_type": feature.feature_type,
                    }
                    for feature in (
                        self.geography.nearest_features(
                            settlement.grid_x, settlement.grid_y,
                            max_distance=12.0, limit=3)
                        if self.geography is not None else []
                    )
                ],
                "description_cn": (
                    f"{year}年，{author.name}在{settlement.name}完成"
                    f"{genre_name}《{work_title}》。抄写者很快制作了数份副本。"
                ),
            })
            if biography_subject is not None:
                event.details.update({
                    "biography_subject_id": biography_subject.id,
                    "biography_subject_name": biography_subject.name,
                    "biography_subject_birth_year": biography_subject.birth_year,
                    "biography_subject_death_year": biography_subject.death_year,
                    "biography_subject_roles": list(biography_subject.roles),
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
            technology = self._stable_event_choice(
                event.id, list(TECHNOLOGY_CATALOG))
            research_process = generate_research_process(
                self.seed,
                event.id,
                technology,
                year,
                settlement.id,
                settlement.name,
                discoverer.id,
                discoverer.name,
            )
            event.title = f"{settlement.name}制成{technology.title}"
            event.person_ids = [discoverer.id]
            event.details.update({
                "discoverer_id": discoverer.id,
                "discoverer_name": discoverer.name,
                "discovery_name": technology.title,
                "technology_key": technology.key,
                "artifact_subtype": technology.artifact_subtype,
                "artifact_display_name": technology.display_name,
                "artifact_material": technology.material,
                "technology_function_cn": technology.function_cn,
                "research_process": research_process,
                "description_cn": (
                    f"{year}年，{discoverer.name}与工匠在{settlement.name}"
                    f"完成了{technology.title}的第一批可重复试制。"
                    f"这套装置用于{technology.function_cn}。"
                ),
            })

    def _stable_event_choice(self, event_id: str, options: list[Any]) -> Any:
        payload = f"{self.seed}|{event_id}".encode("utf-8")
        index = int(hashlib.sha256(payload).hexdigest()[:8], 16)
        return options[index % len(options)]

    def _build_literary_title(
            self, event_id: str, creation_year: int, genre: str,
            settlement: Settlement,
            sources: list[dict[str, Any]],
            subject: Person | None = None) -> str:
        """Combine grounded keywords into a deterministic, non-pool title."""
        event_themes = list(dict.fromkeys(
            event_theme(source.get("event_type")) for source in sources
        ))
        if genre == "biography" and subject is not None:
            role_themes = [
                role_theme(role)
                for role in subject.roles
                if role_theme(role) is not None
            ]
            themes = list(dict.fromkeys(role_themes + event_themes))[:2]
            theme_text = "与".join(themes) if themes else "生平"
            form = self._stable_event_choice(
                f"{event_id}|biography_form",
                ["record", "life", "named"],
            )
            if form == "life":
                base_title = f"{subject.name}{theme_text}生平"
            elif form == "named":
                base_title = f"{subject.name}：{theme_text}录"
            else:
                base_title = f"{subject.name}{theme_text}记"
            return f"{base_title}（{creation_year}年写成）"

        themes = event_themes[:2] or ["历年"]
        theme_text = "与".join(themes)
        nearby = (
            self.geography.nearest_features(
                settlement.grid_x, settlement.grid_y,
                max_distance=12.0, limit=1)
            if self.geography is not None else []
        )
        landscape_name = nearby[0].name if nearby else settlement.name
        if genre == "epic":
            form = self._stable_event_choice(
                f"{event_id}|epic_form", ["长歌", "行记", "归程歌"])
            return f"{landscape_name}{theme_text}{form}（{creation_year}年写成）"
        if genre == "drama":
            form = self._stable_event_choice(
                f"{event_id}|drama_form", ["之问", "两证", "异议剧"])
            return f"{settlement.name}{theme_text}{form}（{creation_year}年写成）"
        if genre == "lyric_cycle":
            form = self._stable_event_choice(
                f"{event_id}|lyric_form", ["短章", "组歌", "十二题"])
            return f"{landscape_name}{theme_text}{form}（{creation_year}年写成）"
        forms = ["编年", "纪事", "年录"]
        form = self._stable_event_choice(
            f"{event_id}|chronicle_form", forms)
        return f"{settlement.name}{theme_text}{form}（{creation_year}年写成）"

    def _select_literary_sources(self, settlement_id: str, year: int,
                                 limit: int = 3) -> list[dict[str, Any]]:
        """Freeze earlier local events that a new work can draw upon."""
        excluded_types = {
            "literary_work", "literary_spread", "theoretical_work",
        }
        narrative_priority = {
            "war": 10, "rebellion": 10, "disaster": 10,
            "raid": 9, "ruler_change": 9, "decline": 9,
            "founding": 8, "treaty": 8, "reconstruction": 8,
            "relief": 8, "discovery": 7, "exploration": 7,
            "construction": 6, "trade": 6, "economic": 6,
            "crime": 5, "duel": 5, "festival": 4,
            "population_milestone": 4, "marriage": 3,
            "notable_birth": 2, "omen": 2,
        }
        candidates = [
            event for event in self.get_settlement_events(settlement_id)
            if event.year < year and event.event_type not in excluded_types
        ]

        def rank(source: HistoricalEvent) -> tuple[float, int, str]:
            priority = narrative_priority.get(source.event_type, 1)
            historical_weight = (
                priority
                + source.importance_score * 4.0
                + source.visibility_score * 2.0
            )
            return historical_weight, source.year, source.id

        selected = sorted(candidates, key=rank, reverse=True)[:limit]
        selected.sort(key=lambda source: (source.year, source.id))
        return [self._snapshot_history_event(source) for source in selected]

    def _select_biography_subject(
            self, settlement_id: str, year: int,
            author_id: str) -> tuple[Person | None, list[dict[str, Any]]]:
        candidates = []
        for person in self.persons.values():
            if (person.id == author_id
                    or person.settlement_id != settlement_id
                    or person.birth_year > year):
                continue
            sources = self._select_person_history(person.id, year, limit=6)
            if not sources:
                continue
            importance = sum(
                float(source.get("importance_score", 0.0))
                for source in sources)
            candidates.append((len(sources), importance, person.id,
                               person, sources))
        if not candidates:
            return None, []
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        _, _, _, subject, sources = candidates[0]
        return subject, sources

    def _select_person_history(self, person_id: str, year: int,
                               limit: int = 6) -> list[dict[str, Any]]:
        excluded_types = {
            "literary_work", "literary_spread", "theoretical_work",
        }
        candidates = [
            event for event in self.events
            if event.year < year and person_id in event.person_ids
            and event.event_type not in excluded_types
        ]
        ranked = sorted(
            candidates,
            key=lambda source: (
                source.importance_score + source.severity,
                source.visibility_score,
                source.year,
                source.id,
            ),
            reverse=True,
        )[:limit]
        ranked.sort(key=lambda source: (source.year, source.id))
        return [
            self._snapshot_history_event(source, person_id)
            for source in ranked
        ]

    def _snapshot_history_event(
            self, source: HistoricalEvent,
            subject_id: str | None = None) -> dict[str, Any]:
        participant_names = [
            self.settlements[participant_id].name
            for participant_id in source.participants
            if participant_id in self.settlements
        ]
        person_names = [
            self.persons[person_id].name
            for person_id in source.person_ids
            if person_id in self.persons
        ]
        snapshot = {
            "event_id": source.id,
            "year": source.year,
            "event_type": source.event_type,
            "title": source.title,
            "summary": source.details.get("description_cn", source.title),
            "participant_names": participant_names,
            "person_names": person_names,
            "importance_score": source.importance_score,
        }
        if subject_id is not None:
            snapshot["subject_role"] = self._person_role_in_event(
                source, subject_id)
        return snapshot

    @staticmethod
    def _person_role_in_event(source: HistoricalEvent,
                              subject_id: str) -> str:
        details = source.details
        role_fields = (
            ("founder_id", "建城者"),
            ("discoverer_id", "研发者"),
            ("rebel_leader_id", "反抗领袖"),
            ("old_ruler_id", "当时的统治者"),
            ("new_ruler_id", "继任者"),
            ("person_id", "事件当事人"),
            ("parent_id", "家长"),
        )
        for field_name, role_name in role_fields:
            if details.get(field_name) == subject_id:
                return role_name
        if subject_id in details.get("commander_ids", []):
            return "军队指挥者"
        if subject_id in details.get("ruler_ids", []):
            return "当时的统治者"
        if subject_id in details.get("signer_ids", []):
            return "签约者"
        return "事件参与者"

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
                religion = primary_religion(stl, self.religions)
                event = self._event_gen.generate_festival_event(
                    year, stl.id, stl.name, religion)
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
                religion = primary_religion(stl, self.religions)
                event = self._event_gen.generate_omen_event(
                    year, stl.id, stl.name, religion)
                self._add_event_with_evidence(event)

            # Religious reform creates a related tradition rather than
            # replacing every local practice at once.
            religion = primary_religion(stl, self.religions)
            recent_reform = any(
                event.event_type == "religious_reform"
                and event.primary_location == stl.id
                and year - event.year < 18
                for event in reversed(self.events))
            reform_roll = int.from_bytes(hashlib.sha256(
                f"religious-reform-roll|{self.seed}|{stl.id}|{year}"
                .encode("utf-8")).digest()[:8], "big") / 2**64
            if (religion is not None and not recent_reform
                    and reform_roll < 0.025 * pop_factor * REDUCTION):
                keeper = self._get_or_create_officeholder(
                    stl.id, year, "priest")
                reasons = (
                    "旧抄本之间的措辞差异", "灾后仪式能否简化的争论",
                    "外来赞歌与本地旧仪的融合", "祭历日期长期不一致",
                )
                reason_index = int.from_bytes(hashlib.sha256(
                    f"reform|{self.seed}|{stl.id}|{year}".encode("utf-8")
                ).digest()[:4], "big") % len(reasons)
                reformed = self._religion_mgr.create_reform(
                    religion, stl, year, reasons[reason_index])
                effects = [
                    ModifyReligiousPresence(
                        stl.id, religion.id, -0.12, "religious_reform"),
                    ModifyReligiousPresence(
                        stl.id, reformed.id, 0.32, "religious_reform"),
                    ModifyReligiousTolerance(
                        stl.id, 0.02, "reform_debate"),
                ]
                effect_ids = self._effect_resolver.apply_effects(effects, self)
                event = self._event_gen.generate_religious_reform_event(
                    year, stl.id, stl.name, religion, reformed,
                    keeper.id, keeper.name)
                event.effect_ids.extend(effect_ids)
                event.effects.extend(effect_to_dict(effect) for effect in effects)
                if int.from_bytes(hashlib.sha256(
                        f"official-reform|{self.seed}|{stl.id}|{year}"
                        .encode("utf-8")).digest()[:2], "big") % 4 == 0:
                    stl.official_religion_id = reformed.id
                self._add_event_with_evidence(event)

            active_traditions = sorted(
                ((value, religion_id)
                 for religion_id, value in stl.religious_presence.items()
                 if value >= 0.12 and religion_id in self.religions),
                reverse=True,
            )
            recent_conflict = any(
                event.event_type == "religious_conflict"
                and event.primary_location == stl.id
                and year - event.year < 20
                for event in reversed(self.events))
            conflict_chance = (
                0.035 * (1.0 - stl.religious_tolerance) * REDUCTION)
            conflict_roll = int.from_bytes(hashlib.sha256(
                f"religious-conflict-roll|{self.seed}|{stl.id}|{year}"
                .encode("utf-8")).digest()[:8], "big") / 2**64
            if (len(active_traditions) >= 2 and not recent_conflict
                    and conflict_roll < conflict_chance):
                dominant = self.religions[active_traditions[0][1]]
                minority = self.religions[active_traditions[1][1]]
                effects = [
                    ModifyStability(stl.id, delta=-0.05,
                                    reason="religious_conflict"),
                    ModifyReligiousTolerance(
                        stl.id, -0.08, "religious_conflict"),
                    ModifyReligiousPresence(
                        stl.id, minority.id, -0.10, "religious_suppression"),
                ]
                effect_ids = self._effect_resolver.apply_effects(effects, self)
                event = self._event_gen.generate_religious_conflict_event(
                    year, stl.id, stl.name, dominant, minority)
                event.effect_ids.extend(effect_ids)
                event.effects.extend(effect_to_dict(effect) for effect in effects)
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
            elif isinstance(effect, StrengthenExchangeNetwork):
                record(effect.settlement_a, "exchange_network", 1)
                record(effect.settlement_b, "exchange_network", 1)
            elif isinstance(effect, FoundSettlement):
                for dimension in ("population", "food", "treasury"):
                    record(effect.source_settlement_id, dimension, -1)
                    record(effect.new_settlement_id, dimension, 1)
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
            both_sides_alive = bool(
                winner is not None and winner.alive
                and loser is not None and loser.alive)
            war_event_id = next((
                event.id for event in reversed(self.events)
                if event.event_type == "war" and event.year == war_year
                and winner_id in event.participants and loser_id in event.participants
            ), None)

            # 战后 2~6 年：可能签订和约
            if 2 <= years_after <= 6 and rng.random() < 0.25:
                if both_sides_alive:
                    event = self._event_gen.generate_treaty_event(
                        year, winner.id, winner.name, loser.id, loser.name,
                        winner.id, "peace")
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._attach_current_rulers(event)
                    self._add_event_with_evidence(event)

            # 战后 1~3 年：可能发生报复袭击
            if 1 <= years_after <= 3 and rng.random() < 0.20:
                if both_sides_alive:
                    event = self._event_gen.generate_raid_event(
                        year, loser.id, loser.name, winner.id, winner.name, winner.id)
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._add_event_with_evidence(event)

            # 战后 5~15 年：可能结盟
            if 5 <= years_after <= 15 and rng.random() < 0.15:
                if both_sides_alive:
                    event = self._event_gen.generate_treaty_event(
                        year, winner.id, winner.name, loser.id, loser.name,
                        winner.id, "alliance")
                    if war_event_id:
                        event.cause_event_ids = [war_event_id]
                    self._attach_current_rulers(event)
                    self._add_event_with_evidence(event)

            # 失效链保留到原期限，以维持既有种子的随机数序列；
            # both_sides_alive 会确保它不再生成任何事件。
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
            ruler = self.persons.get(settlement.ruler_id) \
                if settlement is not None and settlement.alive else None
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
                cultural_network = relationship.exchange_strengths.get(
                    "cultural", 0.0)
                if (relationship.trust < 0.55
                        and relationship.trade_volume <= 0
                        and cultural_network <= 0):
                    continue
                connection_score = (
                    relationship.trust
                    + min(relationship.trade_volume / 100.0, 0.5)
                    + min(cultural_network * 0.25, 0.75))
                partners.append((
                    connection_score,
                    relationship.trade_volume,
                    cultural_network,
                    partner.id,
                    partner,
                ))
            if not partners:
                continue
            partners.sort(key=lambda item: (
                -item[0], -item[1], -item[2], item[3]))
            target = partners[0][4]
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
        transfer_effects = plan_supplemental_event_transfers(self, event)
        if transfer_effects:
            effect_ids = self._effect_resolver.apply_effects(
                transfer_effects, self)
            if effect_ids:
                event.effect_ids.extend(effect_ids)
                event.effects.extend(
                    effect_to_dict(effect) for effect in transfer_effects)
                self._record_effect_sources(event, transfer_effects)
            else:
                event.details.pop("object_transfers", None)
        self._apply_event_person_movements(event)
        self._add_event(event)
        recipes = list(EVIDENCE_RECIPES.get(event.event_type, []))
        if (event.event_type == "construction"
                and event.details.get("building_type") == "temple"):
            settlement = self.settlements.get(event.primary_location)
            religion = (primary_religion(settlement, self.religions)
                        if settlement is not None else None)
            if religion is not None:
                event.details.update({
                    "religion_id": religion.id,
                    "religion_name": religion.name,
                    "doctrine": religion.doctrine,
                    "ritual": religion.primary_ritual,
                    "sacred_symbol": religion.sacred_symbol,
                    "religion_profile": religion.text_profile(),
                })
            recipes.extend(EVIDENCE_RECIPES["cultural"])
        source_records = self._record_gen.create_records_for_event(
            event, recipes, self.settlements, self.persons)
        for record_versions in source_records.values():
            for record in record_versions:
                self.records[record.id] = record
        for evd in self._evidence_gen.create_evidence_for_event(
                event, source_records, recipes):
            self.evidence[evd.id] = evd
            settlement = self.settlements.get(evd.location_id)
            record = self.records.get(evd.source_record_id)
            if settlement is not None:
                self._storage_mgr.assign_evidence(
                    evd, settlement, evd.created_year,
                    owner_person_id=(record.author_person_id if record else None))
            self._informant_mgr.distribute_carrier(
                self, evd, record, event.year)

    def _apply_event_person_movements(self, event: HistoricalEvent) -> None:
        person_effects = plan_event_person_movements(self, event)
        population_effects, population_details = \
            plan_disaster_population_displacement(self, event)
        knowledge_effects, knowledge_details = \
            plan_event_knowledge_transfers(self, event, person_effects)
        network_effects, network_details = plan_event_exchange_networks(
            self, event, person_effects, knowledge_details)
        effects = (
            person_effects + population_effects
            + knowledge_effects + network_effects)
        if not effects:
            event.details.pop("person_movements", None)
            event.details.pop("population_displacement", None)
            event.details.pop("knowledge_transfers", None)
            event.details.pop("network_updates", None)
            return
        effect_ids = self._effect_resolver.apply_effects(effects, self)
        if not effect_ids:
            event.details.pop("person_movements", None)
            event.details.pop("population_displacement", None)
            event.details.pop("knowledge_transfers", None)
            event.details.pop("network_updates", None)
            return
        event.effect_ids.extend(effect_ids)
        event.effects.extend(effect_to_dict(effect) for effect in effects)
        movements = describe_person_movements(self, person_effects)
        if movements:
            event.details["person_movements"] = movements
            event.person_ids = list(dict.fromkeys([
                *event.person_ids,
                *(item["person_id"] for item in movements),
            ]))
        if population_details:
            event.details["population_displacement"] = population_details
        if knowledge_details:
            event.details["knowledge_transfers"] = knowledge_details
            self._record_effect_sources(event, knowledge_effects)
        if network_details:
            event.details["network_updates"] = network_details
            self._record_effect_sources(event, network_effects)

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
            base_subtype = evd.subtype.removesuffix("_copy")
            decay_rng = (
                random.Random(
                    f"religious-decay|{self.seed}|{year}|{evd.id}")
                if base_subtype in RELIGIOUS_CONTENT_SUBTYPES else rng)
            destroyed = tick_natural_decay(evd, climate, decay_rng)
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
            "schema_version": WORLD_SCHEMA_VERSION,
            "seed": self.seed,
            "name": self.name,
            "current_year": self.current_year,
            "settlements": [s.to_dict() for s in self.settlements.values()],
            "polities": [p.to_dict() for p in self.polities.values()],
            "settlement_control_periods": [
                period.to_dict()
                for period in self.settlement_control_periods.values()
            ],
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
            "trade_routes": [
                route.to_dict() for route in self.trade_routes.values()],
            "road_segments": [
                segment.to_dict() for segment in self.road_segments.values()],
            "travel_groups": [
                group.to_dict() for group in self.travel_groups.values()],
            "signposts": [
                signpost.to_dict() for signpost in self.signposts.values()],
            "religions": [
                tradition.to_dict() for tradition in self.religions.values()],
            "historical_sites": [
                site.to_dict() for site in self.historical_sites.values()],
            "burials": [
                burial.to_dict() for burial in self.burials.values()],
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
            "_last_founding_year": dict(self._last_founding_year),
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
        """Restore the current world schema and rebuild runtime managers."""
        source_schema = int(data.get("schema_version", 0))
        if source_schema not in {
                12, 13, 14, 15, 16, 17, WORLD_SCHEMA_VERSION}:
            raise ValueError(
                f"unsupported world schema: {data.get('schema_version')!r}; "
                f"expected {WORLD_SCHEMA_VERSION}")

        required = (
            "seed", "name", "current_year", "settlements", "polities",
            "settlement_control_periods", "events", "evidence", "records",
            "persons", "informants", "knowledge_entries", "storage_sites",
            "event_history_by_settlement", "_last_ruler_change",
            "_pop_milestones", "_recent_war_years",
            "_pending_war_settlements", "_pending_disaster_aftermaths",
            "_pending_literary_spreads", "_last_founding_year",
            "_rule_cooldowns", "_state_cause_sources",
        )
        missing = [key for key in required if key not in data]
        if source_schema == WORLD_SCHEMA_VERSION and "religions" not in data:
            missing.append("religions")
        if source_schema == WORLD_SCHEMA_VERSION:
            for key in (
                    "historical_sites", "burials", "signposts",
                    "road_segments"):
                if key not in data:
                    missing.append(key)
        if missing:
            raise ValueError(
                "incomplete world schema; missing: " + ", ".join(missing))
        _validate_serialized_versions(data)

        w = cls(seed=int(data["seed"]), name=data["name"])
        w.current_year = int(data["current_year"])
        w.settlements = {
            s_data["id"]: Settlement.from_dict(s_data)
            for s_data in data["settlements"]
        }
        w.polities = {
            item["id"]: Polity.from_dict(item) for item in data["polities"]
        }
        w.settlement_control_periods = {
            item["id"]: SettlementControlPeriod.from_dict(item)
            for item in data["settlement_control_periods"]
        }
        w.persons = {
            person_data["id"]: Person.from_dict(person_data)
            for person_data in data["persons"]
        }
        w.informants = {
            item["id"]: Informant.from_dict(item)
            for item in data["informants"]
        }
        w.knowledge_entries = {
            item["id"]: KnowledgeEntry.from_dict(item)
            for item in data["knowledge_entries"]
        }
        w.events = [HistoricalEvent.from_dict(e) for e in data["events"]]
        w.evidence = {
            e_data["id"]: Evidence.from_dict(e_data)
            for e_data in data["evidence"]
        }
        w.storage_sites = {
            site_data["id"]: StorageSite.from_dict(site_data)
            for site_data in data["storage_sites"]
        }
        w.trade_routes = {
            route_data["id"]: TradeRoute.from_dict(route_data)
            for route_data in data.get("trade_routes", [])
        }
        w.road_segments = {
            item["id"]: RoadSegment.from_dict(item)
            for item in data.get("road_segments", [])
        }
        w.travel_groups = {
            group_data["id"]: TravelGroup.from_dict(group_data)
            for group_data in data.get("travel_groups", [])
        }
        w.signposts = {
            item["id"]: Signpost.from_dict(item)
            for item in data.get("signposts", [])
        }
        w.religions = {
            item["id"]: ReligionTradition.from_dict(item)
            for item in data.get("religions", [])
        }
        w.historical_sites = {
            item["id"]: HistoricalSite.from_dict(item)
            for item in data.get("historical_sites", [])
        }
        w.burials = {
            item["id"]: BurialRecord.from_dict(item)
            for item in data.get("burials", [])
        }
        w.records = {
            record_data["id"]: HistoricalRecord.from_dict(record_data)
            for record_data in data["records"]
        }
        w.event_history_by_settlement = {
            k: list(v) for k, v in data["event_history_by_settlement"].items()
        }
        w._last_ruler_change = dict(data["_last_ruler_change"])
        w._pop_milestones = dict(data["_pop_milestones"])
        w._recent_war_years = dict(data["_recent_war_years"])
        w._pending_war_settlements = [
            tuple(item) for item in data["_pending_war_settlements"]]
        w._pending_disaster_aftermaths = list(
            map(tuple, data["_pending_disaster_aftermaths"]))
        w._pending_literary_spreads = list(
            map(tuple, data["_pending_literary_spreads"]))
        w._last_founding_year = dict(data["_last_founding_year"])
        w._rule_cooldowns = {
            event_type: dict(years)
            for event_type, years in data["_rule_cooldowns"].items()
        }
        w._state_cause_sources = {
            settlement_id: dict(sources)
            for settlement_id, sources in data["_state_cause_sources"].items()
        }

        w.geography = Geography(w.seed)
        w.geography.generate()
        if source_schema == 12:
            seen_pairs = set()
            for settlement in sorted(
                    w.settlements.values(), key=lambda item: item.id):
                for partner_id, relationship in sorted(
                        settlement.relationships.items()):
                    pair = tuple(sorted((settlement.id, partner_id)))
                    if pair in seen_pairs or relationship.trade_volume <= 0.0:
                        continue
                    seen_pairs.add(pair)
                    w.ensure_trade_route(pair[0], pair[1])
        for route in w.trade_routes.values():
            w._attach_route_segments(route)
            w._ensure_route_signposts(route)
            if route.status == "active":
                w._ensure_route_caravan(route)
                w._ensure_route_travelers(route)
        if source_schema < WORLD_SCHEMA_VERSION:
            for signpost in w.signposts.values():
                signpost.weather_to(w.current_year, w.seed)
        w._initialize_runtime_managers()
        if not w.religions:
            for settlement in sorted(
                    w.settlements.values(), key=lambda item: item.id):
                tradition = w._religion_mgr.create_origin(
                    settlement, settlement.founded_year)
                settlement.religious_presence = {tradition.id: 1.0}
                settlement.official_religion_id = tradition.id
        w._restore_runtime_manager_state()
        if source_schema < WORLD_SCHEMA_VERSION:
            w._sync_historical_sites()
        w._validate_political_state()
        w._pressures_cache = compute_all_pressures(w)
        return w

    def _restore_runtime_manager_state(self) -> None:
        self._settlement_mgr.counter = _max_numeric_suffix(
            self.settlements, "stl_")
        self._settlement_mgr.used_names = {
            settlement.name for settlement in self.settlements.values()}
        self._event_gen.counter = _max_numeric_suffix(
            (event.id for event in self.events), "event_")
        self._evidence_gen.counter = _max_numeric_suffix(
            self.evidence, "evd_")
        self._record_gen.counter = _max_numeric_suffix(
            self.records, "record_")
        self._person_mgr.counter = _max_numeric_suffix(
            self.persons, "person_")
        self._effect_resolver.effect_counter = _max_numeric_suffix(
            (effect_id for event in self.events
             for effect_id in event.effect_ids),
            "effect_",
        )
        self._polity_mgr.restore_counters(
            self.polities, self.settlement_control_periods)

        for evidence in self.evidence.values():
            written = evidence.content_data.get("written_content")
            if not written:
                continue
            text = "\n".join(
                passage.get("text", "")
                for passage in written.get("passages", ()))
            self._evidence_gen._document_fingerprints.add(
                hashlib.sha256(text.encode("utf-8")).hexdigest())

    def _validate_political_state(self) -> None:
        for settlement in self.settlements.values():
            polity = self.polities.get(settlement.controller_polity_id)
            if polity is None:
                raise ValueError(
                    f"settlement {settlement.id} has no valid controller")
            current = self.get_current_control_period(settlement.id)
            if current is None or current.polity_id != polity.id:
                raise ValueError(
                    f"settlement {settlement.id} has inconsistent control")

        for period in self.settlement_control_periods.values():
            if period.settlement_id not in self.settlements:
                raise ValueError(
                    f"control period {period.id} references missing settlement")
            if period.polity_id not in self.polities:
                raise ValueError(
                    f"control period {period.id} references missing polity")
            if (period.end_year is not None
                    and period.end_year < period.start_year):
                raise ValueError(f"invalid control period {period.id}")

        for polity in self.polities.values():
            if polity.capital_settlement_id not in self.settlements:
                raise ValueError(
                    f"polity {polity.id} references missing capital")
            if polity.ruler_id is not None and polity.ruler_id not in self.persons:
                raise ValueError(
                    f"polity {polity.id} references missing ruler")

        for settlement in self.settlements.values():
            if (settlement.official_religion_id is not None
                    and settlement.official_religion_id not in self.religions):
                raise ValueError(
                    f"settlement {settlement.id} references missing religion")
            unknown = set(settlement.religious_presence) - set(self.religions)
            if unknown:
                raise ValueError(
                    f"settlement {settlement.id} has unknown religions: "
                    + ", ".join(sorted(unknown)))

        for site in self.historical_sites.values():
            if (site.owner_settlement_id
                    and site.owner_settlement_id not in self.settlements):
                raise ValueError(
                    f"historical site {site.id} references missing settlement")

        for route in self.trade_routes.values():
            if route.status not in {"active", "abandoned", "suspended"}:
                raise ValueError(
                    f"trade route {route.id} has invalid status {route.status}")
            if set(route.segment_ids) - set(self.road_segments):
                raise ValueError(
                    f"trade route {route.id} references missing road segments")
        for segment in self.road_segments.values():
            if (abs(segment.cell_a[0] - segment.cell_b[0])
                    + abs(segment.cell_a[1] - segment.cell_b[1]) != 1):
                raise ValueError(
                    f"road segment {segment.id} is not cardinally adjacent")
            if set(segment.route_ids) - set(self.trade_routes):
                raise ValueError(
                    f"road segment {segment.id} references missing routes")
            if segment.status not in {
                    "active", "disused", "overgrown", "ruined"}:
                raise ValueError(
                    f"road segment {segment.id} has invalid status")

        for signpost in self.signposts.values():
            if signpost.builder_settlement_id not in self.settlements:
                raise ValueError(
                    f"signpost {signpost.id} references missing builder")
            board_ids = {item.id for item in signpost.original_boards}
            if board_ids != {item.id for item in signpost.current_boards}:
                raise ValueError(
                    f"signpost {signpost.id} has inconsistent boards")
            for board in signpost.original_boards + signpost.current_boards:
                if board.destination_id not in self.settlements:
                    raise ValueError(
                        f"signpost board {board.id} references missing destination")
                if (board.writer_person_id
                        and board.writer_person_id not in self.persons):
                    raise ValueError(
                        f"signpost board {board.id} references missing writer")
            for repair in signpost.repair_history:
                if repair.board_id not in board_ids:
                    raise ValueError(
                        f"signpost {signpost.id} repair references missing board")
                if (repair.repairer_person_id
                        and repair.repairer_person_id not in self.persons):
                    raise ValueError(
                        f"signpost {signpost.id} repair references missing person")
        for burial in self.burials.values():
            if burial.site_id not in self.historical_sites:
                raise ValueError(
                    f"burial {burial.id} references missing historical site")
            if burial.person_id not in self.persons:
                raise ValueError(
                    f"burial {burial.id} references missing person")
            if (burial.inscription_evidence_id
                    and burial.inscription_evidence_id not in self.evidence):
                raise ValueError(
                    f"burial {burial.id} references missing inscription")

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

def _max_numeric_suffix(values, prefix: str) -> int:
    maximum = 0
    for value in values:
        if not isinstance(value, str) or not value.startswith(prefix):
            continue
        suffix = value[len(prefix):]
        if suffix.isdigit():
            maximum = max(maximum, int(suffix))
    return maximum


def _validate_serialized_versions(data: dict) -> None:
    expected = {
        "settlements": 6,
        "polities": 1,
        "settlement_control_periods": 1,
        "events": 3,
        "evidence": 7,
        "records": 1,
        "persons": 2,
        "informants": 1,
        "knowledge_entries": 1,
        "storage_sites": 1,
    }
    for collection, schema_version in expected.items():
        for item in data[collection]:
            if item.get("schema_version") != schema_version:
                raise ValueError(
                    f"unsupported {collection} schema for "
                    f"{item.get('id', '<unknown>')}: "
                    f"{item.get('schema_version')!r}; expected "
                    f"{schema_version}")
    for item in data.get("religions", []):
        if item.get("schema_version") != 1:
            raise ValueError(
                f"unsupported religions schema for {item.get('id', '<unknown>')}: "
                f"{item.get('schema_version')!r}; expected 1")
    for collection in ("historical_sites", "burials"):
        for item in data.get(collection, []):
            if item.get("schema_version") != 1:
                raise ValueError(
                    f"unsupported {collection} schema for "
                    f"{item.get('id', '<unknown>')}: "
                    f"{item.get('schema_version')!r}; expected 1")
    for item in data.get("signposts", []):
        if item.get("schema_version") != 1:
            raise ValueError(
                f"unsupported signposts schema for "
                f"{item.get('id', '<unknown>')}: "
                f"{item.get('schema_version')!r}; expected 1")
    for item in data.get("road_segments", []):
        if item.get("schema_version") != 1:
            raise ValueError(
                f"unsupported road_segments schema for "
                f"{item.get('id', '<unknown>')}: "
                f"{item.get('schema_version')!r}; expected 1")


def _resolve_target_name(result, world):
    """解析 $TARGET_NAME 占位符——从 participants 中找对手。"""
    opponent_id = result.target_settlement_id
    if opponent_id:
        opponent = world.settlements.get(opponent_id)
        if opponent:
            return opponent.name
    return "邻国"
