"""Geography-driven deterministic local maps for playable world sites."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import dataclass

from simulation.names import generate_unique_name
from simulation.person import public_mobility_status, public_travel_role
from simulation.religion import primary_religion
from simulation.technology import TECHNOLOGY_ARTIFACT_SUBTYPES


TILE_GRASS = 0
TILE_ROAD = 1
TILE_FLOOR = 2
TILE_WALL = 3
TILE_WATER = 4
TILE_RUBBLE = 5
TILE_SHELF = 6
TILE_STALL = 7
TILE_HOME_FLOOR = 8
TILE_SERVICE_FLOOR = 9
TILE_SAND = 10
TILE_FOREST = 11
TILE_ROCK = 12
TILE_FARMLAND = 13
TILE_BRIDGE = 14
TILE_TUNDRA = 15
TILE_MARSH = 16
TILE_FENCE = 17

BLOCKING_TILES = {
    TILE_WALL, TILE_WATER, TILE_RUBBLE, TILE_SHELF, TILE_STALL,
    TILE_FOREST, TILE_ROCK, TILE_FENCE,
}


SITE_ZONE = {
    "library_collection": "library",
    "administrative_archive": "archive",
    "private_collection": "home",
    "temple_repository": "temple",
    "merchant_archive": "market",
    "workshop_store": "workshop",
    "storehouse": "granary",
    "monument_site": "monument",
    "field_site": "field",
}


ACCESSIBILITY_NAMES = {
    "public": "公开区域",
    "supervised": "有人看管",
    "permission": "需取得许可",
    "restricted": "限制查阅",
    "private": "私人保管",
    "buried": "需要发掘",
}


PLACEMENT_PROFILES = {
    "bookshelf": ("书架", "一排按馆藏位置编排的书架。", 6, True),
    "archive_cabinet": ("档案柜", "存放封印文书和公文副本的档案柜。", 5, True),
    "scroll_chest": ("经卷箱", "用于平放卷轴和仪式文书的经卷箱。", 4, True),
    "ledger_shelf": ("账册架", "商会用于分类放置账册的柜架。", 5, True),
    "document_chest": ("文书箱", "用于保存松散文书和私人契约的木箱。", 4, True),
    "collection_chest": ("藏品箱", "保存小型器物的带盖藏品箱。", 4, True),
    "tool_rack": ("工具架", "用于悬挂工具和金属部件的木架。", 5, True),
    "storage_chest": ("储物箱", "仓库中用于分类保管器物的储物箱。", 5, True),
    "debris_search": ("残骸调查区", "散落残骸间可以逐步清理的调查区域。", 6, False),
    "excavation": ("发掘方格", "覆盖层下可能保存材料的发掘方格。", 6, False),
    "stone_display": ("石质文书", "直接陈放或固定在原处的石质书写载体。", 1, True),
    "workbench_display": ("工作台物件", "直接放置在工作台上的器物。", 1, False),
    "ground_object": ("地面物件", "直接留在地面上的可见物件。", 1, False),
    "ground_scatter": ("散落物", "散落在一小片地面上的物件。", 1, False),
    "floor_object": ("大型器物", "直接立放在室内地面上的大型器物。", 1, True),
    "structural": ("建筑遗存", "固定在原位置、无法作为普通物品收纳的遗存。", 1, True),
    "stratigraphic": ("地层剖面", "需要在原位置观察和记录的地层痕迹。", 1, False),
}


DIRECT_ARTIFACT_PLACEMENTS = {
    "scattered_weapons": "ground_scatter",
    "supply_crate_remains": "ground_object",
    "grain_storage_jar": "floor_object",
    "burned_structures": "structural",
    "demonstration_model": "workbench_display",
    "crafted_item": "workbench_display",
    **{
        subtype: "workbench_display"
        for subtype in TECHNOLOGY_ARTIFACT_SUBTYPES
    },
}


def evidence_placement_kind(evidence, site) -> str:
    """Resolve physical form before choosing a map position."""
    if evidence.state == "buried":
        return "excavation"
    if evidence.evidence_type == "structure":
        return "structural"
    if evidence.evidence_type == "environmental":
        return "stratigraphic"
    if evidence.evidence_type == "document":
        if evidence.material == "stone":
            return "stone_display"
        site_type = site.site_type if site is not None else "field_site"
        return {
            "library_collection": "bookshelf",
            "administrative_archive": "archive_cabinet",
            "temple_repository": "scroll_chest",
            "merchant_archive": "ledger_shelf",
            "private_collection": "document_chest",
            "field_site": "debris_search",
        }.get(site_type, "document_chest")
    direct = DIRECT_ARTIFACT_PLACEMENTS.get(evidence.subtype)
    if direct:
        return direct
    site_type = site.site_type if site is not None else "field_site"
    if site_type == "workshop_store":
        return "tool_rack"
    if site_type == "storehouse":
        return "storage_chest"
    if site_type in {"field_site", "monument_site"}:
        return "ground_object"
    return "collection_chest"


def build_evidence_targets(evidence_values, storage_sites,
                           location_id: str) -> list[dict]:
    """Group portable evidence into fixtures and leave in-situ evidence direct."""
    grouped: dict[tuple[str, str], list] = {}
    direct_targets = []
    for evidence in evidence_values:
        if (evidence.location_id != location_id
                or evidence.state == "destroyed"
                or evidence.evidence_type == "oral"):
            continue
        site = storage_sites.get(evidence.container_id)
        placement = evidence_placement_kind(evidence, site)
        capacity = PLACEMENT_PROFILES[placement][2]
        if capacity == 1:
            direct_targets.append({
                "id": evidence.id,
                "kind": "evidence",
                "placement_kind": placement,
                "storage_site_id": evidence.container_id or "",
                "evidence_ids": (evidence.id,),
            })
        else:
            grouped.setdefault(
                (evidence.container_id or "", placement), []).append(evidence)

    targets = direct_targets
    for (site_id, placement), evidence_group in sorted(grouped.items()):
        capacity = PLACEMENT_PROFILES[placement][2]
        ordered = sorted(
            evidence_group, key=lambda item: (item.storage_position, item.id))
        for offset in range(0, len(ordered), capacity):
            ordinal = offset // capacity + 1
            targets.append({
                "id": f"target_{site_id}_{placement}_{ordinal:02d}",
                "kind": "container",
                "placement_kind": placement,
                "storage_site_id": site_id,
                "evidence_ids": tuple(
                    item.id for item in ordered[offset:offset + capacity]),
            })
    return sorted(targets, key=lambda item: item["id"])


LAYOUT_NAMES = {
    "river": "沿河带状",
    "harbor": "滨水港湾",
    "terrace": "山地台阶",
    "woodland": "林间散布",
    "oasis": "水源聚集",
    "radial": "放射街区",
    "grid": "平原街网",
    "frontier": "疏落边地",
}


LANDSCAPE_NAMES = {
    "mountain": "山麓",
    "highland": "高地",
    "forest": "森林边缘",
    "desert": "干旱荒地",
    "scrubland": "灌木旱地",
    "tundra": "寒冷苔原",
    "grassland": "开阔草原",
    "plains": "平原",
    "river_valley": "河谷低地",
}


REQUIRED_BUILDING_TYPES = {
    "hall", "market", "archive", "workshop",
    "inn", "granary", "bakery", "well",
}


INFRASTRUCTURE_BUILDINGS = {
    "temple": ("temple", "神殿", 11, 9),
    "library": ("library", "图书馆", 12, 9),
    "market": ("great_market", "大市场", 13, 9),
    "fortification": ("fortification", "城防门楼", 13, 8),
    "aqueduct": ("aqueduct", "引水渠水院", 13, 7),
    "palace": ("palace", "领主大厅", 13, 10),
}


def infrastructure_condition(level: float) -> str:
    if level <= 0.05:
        return "ruined"
    if level < 0.7:
        return "damaged"
    return "intact"


OCCUPATIONS = (
    ("farmer", "农人", "正把一捆农具搬回住处。"),
    ("weaver", "织工", "衣袖上还沾着细碎的纤维。"),
    ("porter", "搬运工", "肩上垫着一块被磨薄的粗布。"),
    ("baker", "烘焙师", "围裙上留着浅色面粉印。"),
    ("vendor", "摊贩", "正清点随身的钱袋和小秤。"),
    ("water_carrier", "汲水人", "手边放着两只旧木桶。"),
    ("carpenter", "木匠", "腰间挂着木槌和量绳。"),
    ("inn_worker", "客栈帮工", "正赶着处理下一件杂务。"),
    ("laborer", "零工", "靴面沾着道路和工地的尘土。"),
)


DAILY_CHATTER = (
    "“清早的集市最拥挤，想买东西最好别等到钟响以后。”",
    "“东街水井今天排了很长的队。”",
    "“面包房这一炉快出炉了，整条街都闻得到。”",
    "“客栈晚上总有人进出，白天反而安静些。”",
    "“工坊最近一直忙到天黑，路过时当心门口堆着的木料。”",
    "“要找旧文书，可以去档案馆；我平日很少进去。”",
    "“南边的田地路软，刚下过雨时尤其难走。”",
    "“粮仓门前不许久留，搬运车每天要来回好几趟。”",
    "“公共厅堂今天开得早，门口已经有人等着办事了。”",
    "“南街有几间屋子正在补屋顶，走过时留意落下的碎瓦。”",
    "“中午以后工坊那边会很吵，我通常绕东街走。”",
    "“田边的小路能通到南门，不过推车走起来不太方便。”",
    "“这会儿客栈里多半还能找到空位，再晚些就难说了。”",
    "“水井旁边总能听到各种消息，只是未必都靠得住。”",
    "“市场收摊后会留下不少空箱，搬运工第二天才来清走。”",
    "“我只熟悉自己的活计；城里的旧事还是去问专门的人吧。”",
)


@dataclass(frozen=True)
class SettlementMapProfile:
    width: int
    height: int
    layout_type: str
    water_axis: str
    water_side: str
    hub: tuple[int, int]
    entrances: tuple[str, ...]
    base_tile: int
    landscape_type: str
    landscape_name: str
    feature_names: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "layout_type": self.layout_type,
            "layout_name": LAYOUT_NAMES[self.layout_type],
            "water_axis": self.water_axis,
            "water_side": self.water_side,
            "hub": {"x": self.hub[0], "y": self.hub[1]},
            "entrances": list(self.entrances),
            "landscape_type": self.landscape_type,
            "landscape_name": self.landscape_name,
            "feature_names": list(self.feature_names),
        }


@dataclass(frozen=True)
class LocalMapEntity:
    id: str
    kind: str
    x: int
    y: int
    name: str
    subtype: str
    role: str = ""
    role_name: str = ""
    state: str = ""
    material: str = ""
    zone: str = ""
    description_cn: str = ""
    dialogue_cn: str = ""
    accessibility: str = ""
    condition: str = ""
    searched: bool = False
    discovered_count: int = 0
    placement_kind: str = ""
    storage_site_id: str = ""
    blocks_movement: bool = True

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class LocalBuilding:
    id: str
    name: str
    building_type: str
    bounds: tuple[int, int, int, int]
    door: tuple[int, int]
    condition: str = "intact"
    infrastructure_type: str = ""
    infrastructure_level: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "building_type": self.building_type,
            "bounds": list(self.bounds),
            "door": {"x": self.door[0], "y": self.door[1]},
            "condition": self.condition,
            "infrastructure_type": self.infrastructure_type,
            "infrastructure_level": self.infrastructure_level,
        }


class LocalMapBuilder:
    """Build one local map from geography, settlement state, and history."""

    def cemetery_fits(self, world, settlement) -> bool:
        """Use the real layout pass to test space after ordinary buildings."""
        profile = self._profile(world, settlement)
        tiles = [profile.base_tile] * (profile.width * profile.height)
        self._terrain(tiles, profile, world, settlement)
        roads = self._roads(tiles, profile, world, settlement)
        from game.world_cell_map import paint_trade_routes
        roads.update(paint_trade_routes(
            tiles, world, int(settlement.grid_x), int(settlement.grid_y),
            profile.width, profile.height, profile.hub))
        self._land_use(tiles, roads, profile, world, settlement)
        buildings = self._place_buildings(
            tiles, roads, profile, world, settlement)
        return any(item.building_type == "cemetery" for item in buildings)

    def build(self, world, settlement) -> dict:
        profile = self._profile(world, settlement)
        tiles = [profile.base_tile] * (profile.width * profile.height)
        self._terrain(tiles, profile, world, settlement)
        roads = self._roads(tiles, profile, world, settlement)
        from game.world_cell_map import paint_trade_routes, route_signature
        from simulation.historical_sites import site_signature
        roads.update(paint_trade_routes(
            tiles, world, int(settlement.grid_x), int(settlement.grid_y),
            profile.width, profile.height, profile.hub))
        self._land_use(tiles, roads, profile, world, settlement)
        buildings = self._place_buildings(
            tiles, roads, profile, world, settlement)
        zones, zone_candidates = self._zones(
            tiles, roads, buildings, profile)
        if not settlement.alive:
            self._ruin_damage(tiles, profile, world.seed, settlement.id)

        player_start = self._player_start(
            tiles, roads, profile, set())
        occupied = {player_start}
        entities: list[LocalMapEntity] = []
        protected = self._protected_building_cells(buildings)
        blocking_entities: set[tuple[int, int]] = set()
        interaction_targets: set[tuple[int, int]] = set()
        baseline_reached = self._reachable_from(
            tiles, profile, player_start, set())
        required_doors = {
            item.door for item in buildings
            if item.door in baseline_reached}
        zone_indexes: dict[str, int] = {}
        targets = build_evidence_targets(
            world.evidence.values(), world.storage_sites, settlement.id)
        evidence_by_id = world.evidence
        burial_by_evidence = {
            burial.inscription_evidence_id: burial
            for burial in world.burials.values()
            if burial.inscription_evidence_id
        }
        grave_candidates = [
            candidate for candidate in self._grave_candidates(buildings)
            if candidate not in protected
        ]
        grave_index = 0
        for target in targets:
            first_evidence = evidence_by_id[target["evidence_ids"][0]]
            burial = burial_by_evidence.get(first_evidence.id)
            site = world.storage_sites.get(target["storage_site_id"])
            site_type = site.site_type if site is not None else "field_site"
            zone = SITE_ZONE.get(site_type, "field")
            placement = target["placement_kind"]
            label, description, _, blocks_movement = \
                PLACEMENT_PROFILES[placement]
            index_key = f"{zone}:{placement}"
            if burial is not None and grave_candidates:
                available = [
                    candidate for candidate in grave_candidates
                    if candidate not in occupied
                ]
                position = (
                    available[grave_index % len(available)] if available
                    else grave_candidates[grave_index % len(grave_candidates)])
                grave_index += 1
            else:
                candidates = self._placement_candidates(
                    placement, zone, zone_candidates, buildings,
                    roads, tiles, profile)
                position = self._next_evidence_position(
                    candidates, occupied, protected, blocking_entities,
                    required_doors, interaction_targets,
                    zone_indexes.get(index_key, 0),
                    blocks_movement, tiles, profile, player_start)
            zone_indexes[index_key] = zone_indexes.get(index_key, 0) + 1
            occupied.add(position)
            interaction_targets.add(position)
            if blocks_movement and self._walkable(tiles, profile, position):
                blocking_entities.add(position)
            access = site.accessibility if site is not None else "public"
            condition_value = site.condition if site is not None else 1.0
            condition = (
                "完好" if condition_value >= 0.7 else
                "受损" if condition_value >= 0.3 else "严重损坏")
            state = "intact" if condition_value >= 0.7 else (
                "weathered" if condition_value >= 0.3 else "ruined")
            if target["kind"] == "evidence":
                grave_person = (
                    world.persons.get(burial.person_id)
                    if burial is not None else None)
                name = (f"{grave_person.name}的墓碑" if grave_person is not None
                        else first_evidence.physical_features.get(
                            "display_name",
                            first_evidence.subtype.replace("_", " ")))
                subtype = (first_evidence.subtype if burial is not None
                           else first_evidence.evidence_type)
                material = first_evidence.material
                state = first_evidence.state
            else:
                ordinal = int(target["id"].rsplit("_", 1)[-1])
                name = f"第{ordinal}号{label}"
                subtype = placement
                material = ""
            entities.append(LocalMapEntity(
                id=target["id"],
                kind=target["kind"],
                x=position[0],
                y=position[1],
                name=name,
                subtype=subtype,
                role=access,
                role_name=ACCESSIBILITY_NAMES.get(
                    access, access),
                state=state,
                material=material,
                zone=("墓园" if burial is not None else
                      site.name if site is not None else "露天调查区"),
                description_cn=description,
                accessibility=access,
                condition=condition,
                placement_kind=placement,
                storage_site_id=target["storage_site_id"],
                blocks_movement=blocks_movement,
            ))

        temple_fixtures = self._temple_fixtures(
            world, settlement, buildings, occupied, protected,
            tiles, profile)
        entities.extend(temple_fixtures)

        npc_candidates = self._npc_candidates(
            tiles, roads, occupied, profile)
        informants = world.get_available_informants(settlement.id)
        for index, informant in enumerate(informants):
            person = world.persons.get(informant.person_id)
            if person is None:
                continue
            home = world.settlements.get(person.settlement_id)
            travel_name = public_travel_role(person)
            public_status = public_mobility_status(person)
            if public_status == "resident":
                zone = "聚落公共区域"
                description = ""
            elif public_status == "survivor":
                zone = "废墟幸存者营地"
                description = (
                    "一位仍留在此处废墟附近的"
                    f"{travel_name or '幸存者'}。")
            elif public_status == "captive" or not travel_name:
                zone = "聚落公共区域"
                description = f"一位{travel_name or '身份未明的外地人'}。"
            else:
                origin = home.name if home is not None else "外地"
                zone = "外来者停留区"
                description = (
                    f"一位自称来自{origin}的{travel_name or '访客'}。")
            position = self._next_walkable_free(
                npc_candidates, occupied, index, tiles, profile)
            occupied.add(position)
            entities.append(LocalMapEntity(
                id=informant.id,
                kind="informant",
                x=position[0],
                y=position[1],
                name=person.name,
                subtype="person",
                role=informant.role,
                role_name=travel_name,
                state=public_status,
                zone=zone,
                description_cn=description,
            ))
        if settlement.alive:
            entities.extend(self._residents(
                world, settlement, occupied, npc_candidates,
                tiles, profile))
        else:
            entities.extend(self._ruin_survivors(
                world, settlement, occupied, npc_candidates,
                tiles, profile, {item.person_id for item in informants}))

        site_type = "settlement" if settlement.alive else "ruin"
        if not settlement.alive:
            buildings = [LocalBuilding(
                item.id, item.name, item.building_type,
                item.bounds, item.door, "ruined",
                item.infrastructure_type, item.infrastructure_level)
                for item in buildings]
        return {
            "schema_version": 6,
            "site_type": site_type,
            "cell": {
                "x": int(settlement.grid_x), "y": int(settlement.grid_y)},
            "width": profile.width,
            "height": profile.height,
            "profile": profile.to_dict(),
            "tiles": tiles,
            "blocking_tiles": sorted(BLOCKING_TILES),
            "player_start": {"x": player_start[0], "y": player_start[1]},
            "entities": [item.to_dict() for item in entities],
            "decorations": [],
            "discovered_evidence": [],
            "buildings": [item.to_dict() for item in buildings],
            "zones": zones,
            "route_signature": route_signature(
                world, int(settlement.grid_x), int(settlement.grid_y)),
            "historical_site_signature": site_signature(
                world.get_historical_sites_at(
                    int(settlement.grid_x), int(settlement.grid_y))),
        }

    @staticmethod
    def _grave_candidates(
            buildings: list[LocalBuilding]) -> list[tuple[int, int]]:
        cemetery = next((
            building for building in buildings
            if building.building_type == "cemetery"
        ), None)
        if cemetery is None:
            return []
        left, top, right, bottom = cemetery.bounds
        center_x = (left + right) // 2
        return [
            (x, y)
            for y in range(top + 1, bottom, 2)
            for x in range(left + 1, right)
            if x != center_x
        ]

    def _temple_fixtures(
            self, world, settlement, buildings: list[LocalBuilding],
            occupied: set[tuple[int, int]],
            protected: set[tuple[int, int]], tiles: list[int],
            profile: SettlementMapProfile) -> list[LocalMapEntity]:
        religion = primary_religion(settlement, world.religions)
        if religion is None:
            return []
        temples = [
            building for building in buildings
            if building.building_type == "temple"]
        result = []
        fixture_specs = (
            (
                "temple_altar", "仪式祭台", "祭坛",
                f"石台正面刻着{religion.sacred_symbol}。边缘不同年代的"
                "凿痕表明，其陈设曾被多次调整。",
            ),
            (
                "offering_table", "公共供桌", "供物陈设",
                f"桌面残留{religion.offering}的痕迹。依照{religion.name}的仪次，"
                f"此处应由{religion.officiant}收取供物，但痕迹本身不能证明由谁主持。",
            ),
            (
                "votive_wall", "还愿铭记墙", "铭记墙",
                f"墙面回应着“{religion.congregation_response}”的仪式要求。"
                "新旧姓名彼此覆盖，其中一些符号与正式经文并不完全相同。",
            ),
        )
        for temple in temples:
            candidates = [
                item for item in reversed(self._building_candidates(
                    tiles, profile, temple))
                if item not in occupied and item not in protected]
            for index, (subtype, name, role_name, description) in enumerate(
                    fixture_specs):
                if not candidates:
                    break
                position = candidates.pop(0)
                occupied.add(position)
                result.append(LocalMapEntity(
                    id=f"{temple.id}_{subtype}",
                    kind="landmark",
                    x=position[0], y=position[1],
                    name=name, subtype=subtype,
                    role="religious_fixture", role_name=role_name,
                    state=temple.condition,
                    material="stone" if index != 1 else "wood",
                    zone=temple.name,
                    description_cn=description,
                    blocks_movement=False,
                ))
        return result

    def _profile(self, world, settlement) -> SettlementMapProfile:
        peak = max(settlement.population, settlement.peak_population)
        if settlement.size == "city" or peak >= 2000:
            width, height = 144, 96
        elif settlement.size == "town" or peak >= 500:
            width, height = 120, 80
        elif peak < 150:
            width, height = 80, 56
        else:
            width, height = 96, 64

        geography = world.geography
        sx, sy = int(settlement.grid_x), int(settlement.grid_y)
        landscape = self._landscape_type(geography, sx, sy)
        water = []
        river = []
        radius = 10
        for y in range(max(0, sy - radius), min(geography.height, sy + radius + 1)):
            for x in range(max(0, sx - radius), min(geography.width, sx + radius + 1)):
                biome = str(geography.biomes[y, x])
                if biome in {"ocean", "lake", "river"}:
                    water.append((x - sx, y - sy, biome))
                if biome == "river":
                    river.append((x - sx, y - sy))

        nearest = min(water, key=lambda item: abs(item[0]) + abs(item[1])) \
            if water else (0, 0, "")
        if abs(nearest[0]) > abs(nearest[1]):
            water_side = "east" if nearest[0] > 0 else "west"
        else:
            water_side = "south" if nearest[1] > 0 else "north"
        nearest_distance = abs(nearest[0]) + abs(nearest[1])
        if nearest[2] == "river" and nearest_distance <= 1:
            x_span = max(item[0] for item in river) - min(item[0] for item in river)
            y_span = max(item[1] for item in river) - min(item[1] for item in river)
            water_axis = "horizontal" if x_span >= y_span else "vertical"
            layout = "river"
        elif nearest[2] in {"ocean", "lake"} and nearest_distance <= 2:
            water_axis = "vertical" if water_side in {"east", "west"} else "horizontal"
            layout = "harbor"
        elif landscape in {"mountain", "highland"}:
            water_axis = "none"
            layout = "terrace"
        elif landscape == "forest":
            water_axis = "none"
            layout = "woodland"
        elif landscape in {"desert", "scrubland"}:
            water_axis = "none"
            layout = "oasis"
        elif landscape == "tundra":
            water_axis = "none"
            layout = "frontier"
        else:
            water_axis = "none"
            layout = "radial" if self._stable_int(
                str(world.seed), settlement.id, "layout") % 2 else "grid"

        hub_seed = self._stable_int(str(world.seed), settlement.id, "hub")
        hub_x = width // 2 + (hub_seed % 9) - 4
        hub_y = height // 2 + ((hub_seed // 13) % 7) - 3
        if layout == "harbor":
            shift_x = -width // 8 if water_side == "east" else width // 8 \
                if water_side == "west" else 0
            shift_y = -height // 8 if water_side == "south" else height // 8 \
                if water_side == "north" else 0
            hub_x += shift_x
            hub_y += shift_y
        entrances = self._entrance_directions(world, settlement)
        base_tile = TILE_SAND if landscape in {
            "desert", "scrubland"} else (
            TILE_TUNDRA if landscape == "tundra" else TILE_GRASS)
        feature_types = {
            "river": {"river"},
            "harbor": {"lake"},
            "terrace": {"mountain"},
            "woodland": {"forest"},
            "oasis": {"desert"},
            "frontier": {"tundra"},
        }.get(layout, {"plains"})
        nearby_features = geography.nearest_features(
            sx, sy, feature_types, max_distance=10.0, limit=2)
        feature_names = tuple(feature.name for feature in nearby_features)
        landscape_name = (
            feature_names[0] if feature_names else
            LANDSCAPE_NAMES.get(landscape, landscape)
        )
        return SettlementMapProfile(
            width, height, layout, water_axis, water_side,
            (hub_x, hub_y), entrances, base_tile, landscape,
            landscape_name, feature_names)

    def _landscape_type(self, geography, sx: int, sy: int) -> str:
        scores: dict[str, float] = {}
        radius = 6
        for y in range(max(0, sy - radius), min(geography.height, sy + radius + 1)):
            for x in range(max(0, sx - radius), min(geography.width, sx + radius + 1)):
                biome = str(geography.biomes[y, x])
                if biome in {"ocean", "lake", "river"}:
                    continue
                distance = math.hypot(x - sx, y - sy)
                weight = 1.0 / (1.0 + distance * 0.28)
                if biome == "river_valley":
                    weight *= 0.45
                scores[biome] = scores.get(biome, 0.0) + weight
        if not scores:
            return str(geography.biomes[sy, sx])
        return max(scores, key=lambda biome: (scores[biome], biome))

    def _entrance_directions(self, world, settlement) -> tuple[str, ...]:
        others = sorted(
            (item for item in world.settlements.values()
             if item.id != settlement.id),
            key=lambda item: math.hypot(
                int(item.grid_x) - int(settlement.grid_x),
                int(item.grid_y) - int(settlement.grid_y)),
        )[:4]
        directions = []
        for other in others:
            dx = int(other.grid_x) - int(settlement.grid_x)
            dy = int(other.grid_y) - int(settlement.grid_y)
            direction = (
                "east" if dx > 0 else "west") if abs(dx) >= abs(dy) else (
                "south" if dy > 0 else "north")
            if direction not in directions:
                directions.append(direction)
        for fallback in ("south", "north", "east", "west"):
            if len(directions) >= 3:
                break
            if fallback not in directions:
                directions.append(fallback)
        return tuple(directions)

    def _terrain(self, tiles: list[int], profile: SettlementMapProfile,
                 world, settlement) -> None:
        width, height = profile.width, profile.height
        seed = world.seed
        river_phase = self._phase(seed, settlement.id, "river")
        if profile.layout_type == "river":
            if profile.water_axis == "vertical":
                base = width * (2 if profile.water_side == "east" else 1) // 3
                for y in range(height):
                    center = base + int(math.sin(y / 7.0 + river_phase) * 3)
                    for x in range(center - 1, center + 2):
                        self._set(tiles, profile, x, y, TILE_WATER)
            else:
                base = height * (2 if profile.water_side == "south" else 1) // 3
                for x in range(width):
                    center = base + int(math.sin(x / 8.0 + river_phase) * 3)
                    for y in range(center - 1, center + 2):
                        self._set(tiles, profile, x, y, TILE_WATER)
        elif profile.layout_type == "harbor":
            depth = max(7, min(width, height) // 8)
            for y in range(height):
                for x in range(width):
                    distance = {
                        "west": x, "east": width - 1 - x,
                        "north": y, "south": height - 1 - y,
                    }[profile.water_side]
                    wave = int(math.sin((x + y) / 7.0) * 2)
                    if distance < depth + wave:
                        self._set(tiles, profile, x, y, TILE_WATER)

        center_elevation = float(world.geography.heightmap[
            int(settlement.grid_y), int(settlement.grid_x)])
        forest_phase = self._phase(seed, settlement.id, "forest")
        rock_phase = self._phase(seed, settlement.id, "rock")
        wet_phase = self._phase(seed, settlement.id, "wet")
        hub_x, hub_y = profile.hub
        for y in range(height):
            for x in range(width):
                index = y * width + x
                if tiles[index] == TILE_WATER:
                    continue
                biome, elevation, rainfall, _ = self._local_geography(
                    world.geography, settlement, profile, x, y)
                radial = math.hypot(
                    (x - hub_x) / max(1.0, width * 0.50),
                    (y - hub_y) / max(1.0, height * 0.50),
                )
                outskirts = max(0.0, min(1.0, (radial - 0.22) / 0.70))

                if biome == "tundra":
                    tiles[index] = TILE_TUNDRA
                elif biome in {"desert", "scrubland"} or rainfall < 42.0:
                    tiles[index] = TILE_SAND
                else:
                    tiles[index] = TILE_GRASS

                forest_noise = self._wave_noise(
                    x, y, 10.0, forest_phase)
                rock_noise = self._wave_noise(
                    x, y, 12.0, rock_phase)
                wet_noise = self._wave_noise(
                    x, y, 9.0, wet_phase)
                relief = max(0.0, elevation - center_elevation)
                rock_score = (
                    (0.76 if biome == "mountain" else
                     0.56 if biome == "highland" else 0.04)
                    + max(0.0, elevation - 0.62) * 1.25
                    + relief * 1.4
                    + rock_noise * 0.24
                    + outskirts * 0.12
                )
                forest_score = (
                    (0.68 if biome == "forest" else
                     0.22 if rainfall >= 170.0 else 0.03)
                    + forest_noise * 0.30
                    + outskirts * 0.13
                )
                wet_score = (
                    (0.67 if biome in {"lake", "river"} else
                     0.28 if biome == "river_valley" and rainfall >= 125.0
                     else 0.02)
                    + wet_noise * 0.27
                    + outskirts * 0.08
                )
                if radial > 0.32 and rock_score >= 0.79:
                    tiles[index] = TILE_ROCK
                elif radial > 0.30 and forest_score >= 0.79:
                    tiles[index] = TILE_FOREST
                elif radial > 0.38 and wet_score >= 0.82:
                    tiles[index] = TILE_MARSH

    def _land_use(self, tiles: list[int], roads: set[tuple[int, int]],
                  profile: SettlementMapProfile, world, settlement) -> None:
        width, height = profile.width, profile.height
        distances = [-1] * (width * height)
        queue = deque()
        for x, y in roads:
            distances[y * width + x] = 0
            queue.append((x, y))
        while queue:
            x, y = queue.popleft()
            distance = distances[y * width + x]
            if distance >= 7:
                continue
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                index = ny * width + nx
                if distances[index] != -1:
                    continue
                distances[index] = distance + 1
                queue.append((nx, ny))

        phase = self._phase(world.seed, settlement.id, "fields")
        hub_x, hub_y = profile.hub
        fertility_by_biome = {
            "river_valley": 0.95, "grassland": 0.80,
            "plains": 0.68, "forest": 0.48,
            "scrubland": 0.30, "highland": 0.25,
            "tundra": 0.10, "desert": 0.06,
        }
        for y in range(height):
            for x in range(width):
                index = y * width + x
                road_distance = distances[index]
                if tiles[index] != TILE_GRASS or not 2 <= road_distance <= 7:
                    continue
                radial = math.hypot(
                    (x - hub_x) / max(1.0, width * 0.50),
                    (y - hub_y) / max(1.0, height * 0.50),
                )
                if radial < 0.48:
                    continue
                biome, _, rainfall, temperature = self._local_geography(
                    world.geography, settlement, profile, x, y)
                rain_fit = max(0.0, 1.0 - abs(rainfall - 135.0) / 125.0)
                temp_fit = max(0.0, 1.0 - abs(temperature - 14.0) / 25.0)
                fertility = (
                    fertility_by_biome.get(biome, 0.35) * 0.62
                    + rain_fit * 0.23 + temp_fit * 0.15
                )
                field_score = (
                    self._wave_noise(x, y, 11.0, phase)
                    + fertility * 0.45
                    + (7 - road_distance) * 0.018
                )
                if fertility >= 0.42 and field_score >= 0.80:
                    tiles[index] = TILE_FARMLAND

    def _local_geography(self, geography, settlement,
                         profile: SettlementMapProfile,
                         x: int, y: int) -> tuple[str, float, float, float]:
        span_x = 6.0
        span_y = 5.0
        world_x = float(settlement.grid_x) + (
            x / max(1, profile.width - 1) * 2.0 - 1.0) * span_x
        world_y = float(settlement.grid_y) + (
            y / max(1, profile.height - 1) * 2.0 - 1.0) * span_y
        sample_x = max(0, min(geography.width - 1, round(world_x)))
        sample_y = max(0, min(geography.height - 1, round(world_y)))
        biome = str(geography.biomes[sample_y, sample_x])
        return (
            biome,
            self._sample_numeric(geography.heightmap, world_x, world_y),
            self._sample_numeric(geography.rainfall, world_x, world_y),
            self._sample_numeric(geography.temperature, world_x, world_y),
        )

    @staticmethod
    def _sample_numeric(values, x: float, y: float) -> float:
        height, width = values.shape
        x = max(0.0, min(width - 1.0, x))
        y = max(0.0, min(height - 1.0, y))
        left, top = int(math.floor(x)), int(math.floor(y))
        right, bottom = min(width - 1, left + 1), min(height - 1, top + 1)
        fx, fy = x - left, y - top
        upper = float(values[top, left]) * (1.0 - fx) + float(
            values[top, right]) * fx
        lower = float(values[bottom, left]) * (1.0 - fx) + float(
            values[bottom, right]) * fx
        return upper * (1.0 - fy) + lower * fy

    @staticmethod
    def _wave_noise(x: int, y: int, scale: float, phase: float) -> float:
        value = (
            0.50
            + math.sin(x / scale + phase) * 0.20
            + math.cos(y / (scale * 0.83) - phase * 0.7) * 0.17
            + math.sin((x + y) / (scale * 1.37) + phase * 1.9) * 0.11
        )
        return max(0.0, min(1.0, value))

    def _phase(self, seed: int, settlement_id: str, layer: str) -> float:
        return (
            self._stable_int(str(seed), settlement_id, layer) / 0xFFFFFFFF
        ) * math.tau

    def _roads(self, tiles: list[int], profile: SettlementMapProfile,
               world, settlement) -> set[tuple[int, int]]:
        roads: set[tuple[int, int]] = set()
        entrances = [
            self._entrance_point(profile, direction, world.seed, settlement.id)
            for direction in profile.entrances
        ]
        for index, entrance in enumerate(entrances):
            self._carve_path(
                tiles, roads, profile, entrance, profile.hub,
                self._stable_int(settlement.id, "entrance", str(index)))

        hub_x, hub_y = profile.hub
        if profile.layout_type == "grid":
            for offset in (-12, 0, 12):
                self._carve_path(tiles, roads, profile,
                                 (3, hub_y + offset),
                                 (profile.width - 4, hub_y + offset), offset)
            for offset in (-16, 0, 16):
                self._carve_path(tiles, roads, profile,
                                 (hub_x + offset, 3),
                                 (hub_x + offset, profile.height - 4), offset)
        elif profile.layout_type == "terrace":
            for y in range(10, profile.height - 8, 12):
                left, right = (7, profile.width - 8) if (y // 12) % 2 else (
                    profile.width - 8, 7)
                self._carve_path(tiles, roads, profile,
                                 (left, y), (right, y), y)
        elif profile.layout_type == "frontier":
            self._carve_path(
                tiles, roads, profile,
                (4, hub_y), (profile.width - 5, hub_y), hub_y)
            branch_x = max(8, min(profile.width - 9, hub_x + 9))
            self._carve_path(
                tiles, roads, profile,
                (branch_x, max(4, hub_y - 13)),
                (branch_x, min(profile.height - 5, hub_y + 13)),
                branch_x)
        elif profile.layout_type in {"radial", "oasis"}:
            radius_x = max(12, profile.width // 5)
            radius_y = max(9, profile.height // 5)
            self._carve_ring(tiles, roads, profile, profile.hub,
                             radius_x, radius_y)
        elif profile.layout_type == "river":
            if profile.water_axis == "vertical":
                # Crossing streets must run perpendicular to the river.  The
                # previous orientation produced roads along each bank and no
                # guaranteed way across the water.
                for y in (profile.height // 3, profile.height * 2 // 3):
                    self._carve_path(tiles, roads, profile,
                                     (3, y), (profile.width - 4, y), y)
            else:
                for x in (profile.width // 3, profile.width * 2 // 3):
                    self._carve_path(tiles, roads, profile,
                                     (x, 3), (x, profile.height - 4), x)
        else:
            self._carve_ring(tiles, roads, profile, profile.hub,
                             max(12, profile.width // 5),
                             max(9, profile.height // 5))
        return roads

    def _entrance_point(self, profile: SettlementMapProfile, direction: str,
                        seed: int, settlement_id: str) -> tuple[int, int]:
        offset = self._stable_int(str(seed), settlement_id, direction) % 21 - 10
        hub_x, hub_y = profile.hub
        if direction == "north":
            return max(3, min(profile.width - 4, hub_x + offset)), 1
        if direction == "south":
            return max(3, min(profile.width - 4, hub_x + offset)), profile.height - 2
        if direction == "west":
            return 1, max(3, min(profile.height - 4, hub_y + offset))
        return profile.width - 2, max(3, min(profile.height - 4, hub_y + offset))

    def _carve_path(self, tiles: list[int], roads: set[tuple[int, int]],
                    profile: SettlementMapProfile, start: tuple[int, int],
                    end: tuple[int, int], seed: int) -> None:
        x, y = start
        target_x, target_y = end
        horizontal_first = seed % 2 == 0
        while (x, y) != (target_x, target_y):
            self._paint_road(tiles, roads, profile, x, y)
            move_x = x != target_x
            move_y = y != target_y
            if move_x and move_y:
                use_x = horizontal_first if (abs(x - target_x) + abs(y - target_y)) % 5 else not horizontal_first
            else:
                use_x = move_x
            if use_x:
                x += 1 if target_x > x else -1
            else:
                y += 1 if target_y > y else -1
        self._paint_road(tiles, roads, profile, x, y)

    def _carve_ring(self, tiles: list[int], roads: set[tuple[int, int]],
                    profile: SettlementMapProfile, center: tuple[int, int],
                    radius_x: int, radius_y: int) -> None:
        cx, cy = center
        corners = [
            (cx - radius_x, cy - radius_y),
            (cx + radius_x, cy - radius_y),
            (cx + radius_x, cy + radius_y),
            (cx - radius_x, cy + radius_y),
        ]
        for index in range(4):
            self._carve_path(
                tiles, roads, profile, corners[index],
                corners[(index + 1) % 4], index)

    def _paint_road(self, tiles: list[int], roads: set[tuple[int, int]],
                    profile: SettlementMapProfile, x: int, y: int) -> None:
        for px, py in ((x, y), (x + 1, y)):
            if not (0 <= px < profile.width and 0 <= py < profile.height):
                continue
            index = py * profile.width + px
            tiles[index] = (
                TILE_BRIDGE
                if tiles[index] in {TILE_WATER, TILE_BRIDGE}
                else TILE_ROAD
            )
            roads.add((px, py))

    def _place_buildings(self, tiles: list[int], roads: set[tuple[int, int]],
                         profile: SettlementMapProfile, world,
                         settlement) -> list[LocalBuilding]:
        seed = world.seed
        specs = [
            ("hall", "公共厅堂", 11, 9),
            ("market", "集市会馆", 11, 8),
            ("archive", "档案馆", 11, 9),
            ("workshop", "工坊", 11, 8),
            ("inn", "旅人客栈", 9, 7),
            ("granary", "公共粮仓", 9, 7),
            ("bakery", "街角面包房", 8, 7),
            ("well", "公共水井", 5, 5),
        ]
        if profile.layout_type in {"river", "harbor"}:
            specs.append(("dock", "河岸码头", 10, 7))
        if profile.landscape_type in {"mountain", "highland"}:
            specs.append(("quarry", "采石场", 10, 7))
        elif profile.landscape_type == "forest":
            specs.append(("lumberyard", "木材场", 10, 7))
        elif profile.landscape_type in {"desert", "scrubland"}:
            specs.append(("cistern", "蓄水院", 9, 7))
        else:
            specs.append(("mill", "磨坊", 9, 7))
        infrastructure_specs = []
        for infrastructure_type, (kind, base_name, width, height) in (
                INFRASTRUCTURE_BUILDINGS.items()):
            if infrastructure_type not in settlement.infrastructure:
                continue
            level = float(settlement.infrastructure[infrastructure_type])
            condition = infrastructure_condition(level)
            size_bonus = min(2, max(0, int(level - 1.0)))
            condition_prefix = {
                "damaged": "受损的",
                "ruined": "废弃的",
            }.get(condition, "")
            upgrade_prefix = "扩建的" if level >= 2.0 else ""
            infrastructure_specs.append((
                kind, f"{condition_prefix or upgrade_prefix}{base_name}",
                width + size_bonus, height + size_bonus,
                infrastructure_type, level, condition,
            ))
        cemetery = next((
            site for site in world.get_historical_sites_at(
                int(settlement.grid_x), int(settlement.grid_y))
            if site.site_type == "cemetery"
            and site.owner_settlement_id == settlement.id
        ), None)
        if cemetery is not None:
            cemetery_condition = (
                "ruined" if cemetery.state in {"abandoned", "ruined"}
                else "damaged" if cemetery.state == "damaged" else "intact")
            infrastructure_specs.append((
                "cemetery", cemetery.name, 6, 8,
                "historical_site", cemetery.condition,
                cemetery_condition,
            ))

        cemetery_specs = [
            item for item in infrastructure_specs if item[0] == "cemetery"]
        specs.extend(
            (kind, name, width, height)
            for kind, name, width, height, _, _, _ in infrastructure_specs
            if kind != "cemetery")

        peak = max(settlement.population, settlement.peak_population)
        size_bonus = {"village": 0, "town": 5, "city": 12}.get(
            settlement.size, 0)
        home_count = min(28, 8 + peak // 220 + size_bonus)
        specs.extend(
            ("home", f"民居 {index + 1}", 7, 6)
            for index in range(home_count))
        # A cemetery may use only land left after civic buildings and homes.
        specs.extend(
            (kind, name, width, height)
            for kind, name, width, height, _, _, _ in cemetery_specs)

        buildings = []
        reserved: set[tuple[int, int]] = set()
        infrastructure_by_kind = {
            item[0]: item[4:] for item in infrastructure_specs}
        for index, (kind, name, width, height) in enumerate(specs):
            infrastructure_type, level, condition = (
                infrastructure_by_kind.get(kind, ("", 0.0, "intact")))
            building = self._find_lot(
                tiles, roads, reserved, profile,
                kind, name, width, height,
                self._stable_int(str(seed), settlement.id, kind, str(index)),
                index, condition, infrastructure_type, level,
            )
            if building is None:
                continue
            buildings.append(building)
            left, top, right, bottom = building.bounds
            reserved.update(
                (x, y) for y in range(top, bottom + 1)
                for x in range(left, right + 1))
            self._paint_building(tiles, profile, building)
        return buildings

    def _find_lot(self, tiles: list[int], roads: set[tuple[int, int]],
                  reserved: set[tuple[int, int]], profile: SettlementMapProfile,
                  kind: str, name: str, width: int, height: int,
                  seed: int, ordinal: int, condition: str = "intact",
                  infrastructure_type: str = "",
                  infrastructure_level: float = 0.0) -> LocalBuilding | None:
        candidates = sorted(roads, key=lambda item: (item[1], item[0]))
        if not candidates:
            return None
        start = seed % len(candidates)
        step = 7
        while math.gcd(step, len(candidates)) != 1:
            step += 2
        search_count = (
            len(candidates) if (
                kind in REQUIRED_BUILDING_TYPES or infrastructure_type)
            else min(len(candidates), 512)
        )
        directions = ("north", "south", "west", "east")
        for offset in range(search_count):
            # A coprime stride spreads early attempts across the road network
            # while still visiting every candidate for required buildings.
            road_x, road_y = candidates[(start + offset * step) % len(candidates)]
            for direction_offset in range(4):
                direction = directions[(seed + direction_offset) % 4]
                if direction == "north":
                    left = road_x - width // 2
                    top = road_y - height
                    door = (road_x, road_y - 1)
                elif direction == "south":
                    left = road_x - width // 2
                    top = road_y + 1
                    door = (road_x, road_y + 1)
                elif direction == "west":
                    left = road_x - width
                    top = road_y - height // 2
                    door = (road_x - 1, road_y)
                else:
                    left = road_x + 2
                    top = road_y - height // 2
                    door = (road_x + 2, road_y)
                right, bottom = left + width - 1, top + height - 1
                if left < 2 or top < 2 or right >= profile.width - 2 or bottom >= profile.height - 2:
                    continue
                footprint = {
                    (x, y) for y in range(top, bottom + 1)
                    for x in range(left, right + 1)}
                if footprint & reserved or footprint & roads:
                    continue
                if any(tiles[y * profile.width + x] in {
                        TILE_WATER, TILE_BRIDGE, TILE_RUBBLE}
                       for x, y in footprint):
                    continue
                return LocalBuilding(
                    f"{kind}_{ordinal:02d}", name, kind,
                    (left, top, right, bottom), door, condition,
                    infrastructure_type, infrastructure_level)
        return None

    def _paint_building(self, tiles: list[int], profile: SettlementMapProfile,
                        building: LocalBuilding) -> None:
        left, top, right, bottom = building.bounds
        if building.building_type == "cemetery":
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    edge = x in {left, right} or y in {top, bottom}
                    tile = TILE_FENCE if edge else profile.base_tile
                    if (building.condition in {"damaged", "ruined"}
                            and edge
                            and self._stable_int(
                                building.id, str(x), str(y)) % 5 == 0):
                        tile = profile.base_tile
                    self._set(tiles, profile, x, y, tile)
            center_x = (left + right) // 2
            for y in range(top + 1, bottom + 1):
                self._set(tiles, profile, center_x, y, TILE_SERVICE_FLOOR)
            self._set(
                tiles, profile, building.door[0], building.door[1],
                TILE_SERVICE_FLOOR)
            return
        if building.building_type == "well":
            for y in range(top, bottom + 1):
                for x in range(left, right + 1):
                    self._set(tiles, profile, x, y, TILE_SERVICE_FLOOR)
            self._set(
                tiles, profile, (left + right) // 2,
                (top + bottom) // 2, TILE_WATER)
            return
        floor = TILE_HOME_FLOOR if building.building_type == "home" else (
            TILE_SERVICE_FLOOR if building.building_type in {
                "inn", "bakery", "granary", "market", "great_market",
                "dock", "mill", "quarry", "lumberyard", "cistern",
                "aqueduct"} else TILE_FLOOR)
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                edge = x in {left, right} or y in {top, bottom}
                self._set(tiles, profile, x, y, TILE_WALL if edge else floor)
        self._set(tiles, profile, building.door[0], building.door[1], floor)

        if building.building_type in {"archive", "library"}:
            for y in range(top + 2, bottom - 1):
                self._set(tiles, profile, left + 2, y, TILE_SHELF)
                self._set(tiles, profile, right - 2, y, TILE_SHELF)
        elif building.building_type in {
                "workshop", "granary", "market", "great_market"}:
            for x in range(left + 2, right - 1, 3):
                self._set(tiles, profile, x, top + 2, TILE_STALL)
                if building.building_type == "great_market":
                    self._set(tiles, profile, x, bottom - 2, TILE_STALL)
        elif building.building_type == "aqueduct":
            channel_y = (top + bottom) // 2
            for x in range(left + 2, right - 1):
                self._set(tiles, profile, x, channel_y, TILE_WATER)
        elif building.building_type == "fortification":
            for x, y in (
                    (left + 2, top + 2), (right - 2, top + 2),
                    (left + 2, bottom - 2), (right - 2, bottom - 2)):
                self._set(tiles, profile, x, y, TILE_WALL)
        elif building.building_type == "palace":
            for x in range(left + 3, right - 2):
                self._set(tiles, profile, x, top + 3, TILE_WALL)

        if building.condition in {"damaged", "ruined"}:
            spacing = 5 if building.condition == "damaged" else 3
            for x in range(left + 1, right):
                if (x + top + left) % spacing == 0:
                    self._set(tiles, profile, x, top, TILE_RUBBLE)
            self._set(tiles, profile, building.door[0], building.door[1], floor)

    def _zones(self, tiles: list[int], roads: set[tuple[int, int]],
               buildings: list[LocalBuilding],
               profile: SettlementMapProfile) -> tuple[list[dict], dict]:
        zones = []
        candidates: dict[str, list[tuple[int, int]]] = {}
        primary = {
            "archive": "档案馆", "workshop": "工坊",
            "hall": "公共厅堂", "market": "集市",
            "library": "图书馆", "great_market": "大市场",
            "fortification": "城防门楼", "aqueduct": "引水渠水院",
            "palace": "领主大厅",
        }
        for kind, name in primary.items():
            building = next(
                (item for item in buildings if item.building_type == kind), None)
            if building is None:
                continue
            zones.append({
                "id": kind, "name": name,
                "bounds": list(building.bounds), "show_label": True})
            candidates[kind] = self._building_candidates(
                tiles, profile, building)
        for kind in ("home", "granary", "temple"):
            positions = []
            for building in buildings:
                if building.building_type == kind:
                    positions.extend(self._building_candidates(
                        tiles, profile, building))
            if positions:
                candidates[kind] = positions

        hub_x, hub_y = profile.hub
        monument = self._walkable_near(
            tiles, profile, (hub_x, hub_y), 7)
        farmland = [
            (x, y) for y in range(profile.height)
            for x in range(profile.width)
            if tiles[y * profile.width + x] == TILE_FARMLAND
        ]
        if farmland:
            field_origin = (
                round(sum(item[0] for item in farmland) / len(farmland)),
                round(sum(item[1] for item in farmland) / len(farmland)),
            )
            field = sorted(farmland, key=lambda item: (
                abs(item[0] - field_origin[0])
                + abs(item[1] - field_origin[1]),
                item[1], item[0],
            ))
        else:
            field_origin = self._entrance_point(
                profile, profile.entrances[0], 0, "field")
            field = self._walkable_near(tiles, profile, field_origin, 12)
        public = [item for item in sorted(roads) if self._walkable(
            tiles, profile, item)]
        candidates["monument"] = monument or public
        candidates["field"] = field or public
        for required in (
                "archive", "workshop", "hall", "market", "home", "granary",
                "temple", "library"):
            candidates.setdefault(required, public)
        zones.extend([
            {"id": "monument", "name": "中心纪念地",
             "bounds": [hub_x - 4, hub_y - 3, hub_x + 4, hub_y + 3],
             "show_label": False},
            {"id": "field", "name": "城外调查区",
             "bounds": [max(0, field_origin[0] - 8), max(0, field_origin[1] - 5),
                        min(profile.width - 1, field_origin[0] + 8),
                        min(profile.height - 1, field_origin[1] + 5)],
             "show_label": False},
        ])
        return zones, candidates

    def _building_candidates(self, tiles: list[int],
                             profile: SettlementMapProfile,
                             building: LocalBuilding) -> list[tuple[int, int]]:
        left, top, right, bottom = building.bounds
        positions = [
            (x, y) for y in range(top + 1, bottom)
            for x in range(left + 1, right)
            if self._walkable(tiles, profile, (x, y))]
        positions.sort(key=lambda item: (
            abs(item[0] - building.door[0]) + abs(item[1] - building.door[1]),
            item[1], item[0]))
        return positions

    def _protected_building_cells(
            self, buildings: list[LocalBuilding]) -> set[tuple[int, int]]:
        """Keep doors and short interior aisles clear of generated fixtures."""
        protected: set[tuple[int, int]] = set()
        for building in buildings:
            left, top, right, bottom = building.bounds
            door_x, door_y = building.door
            if door_y == top:
                inward, sideways = (0, 1), (1, 0)
            elif door_y == bottom:
                inward, sideways = (0, -1), (1, 0)
            elif door_x == left:
                inward, sideways = (1, 0), (0, 1)
            else:
                inward, sideways = (-1, 0), (0, 1)
            protected.add(building.door)
            protected.add((door_x - inward[0], door_y - inward[1]))
            for depth in range(1, 4):
                center = (
                    door_x + inward[0] * depth,
                    door_y + inward[1] * depth,
                )
                protected.add(center)
                if depth <= 2:
                    protected.add((
                        center[0] + sideways[0],
                        center[1] + sideways[1],
                    ))
                    protected.add((
                        center[0] - sideways[0],
                        center[1] - sideways[1],
                    ))
        return protected

    def _placement_candidates(
            self, placement: str, zone: str,
            zone_candidates: dict[str, list[tuple[int, int]]],
            buildings: list[LocalBuilding], roads: set[tuple[int, int]],
            tiles: list[int], profile: SettlementMapProfile,
    ) -> list[tuple[int, int]]:
        effective_zone = zone
        matching_buildings = [
            item for item in buildings if item.building_type == zone]
        if (not matching_buildings
                and placement in {"bookshelf", "scroll_chest"}
                and zone in {"library", "temple"}):
            effective_zone = "archive"
            matching_buildings = [
                item for item in buildings
                if item.building_type == effective_zone]
        if placement == "bookshelf" and matching_buildings:
            shelves = []
            for building in matching_buildings:
                left, top, right, bottom = building.bounds
                shelves.extend(
                    (x, y)
                    for y in range(top + 1, bottom)
                    for x in range(left + 1, right)
                    if tiles[y * profile.width + x] == TILE_SHELF
                )
            if shelves:
                return sorted(shelves, key=lambda item: (item[1], item[0]))

        candidates = list(zone_candidates.get(
            effective_zone, zone_candidates.get("field", ())))
        fixture_types = {
            "archive_cabinet", "scroll_chest", "ledger_shelf",
            "document_chest", "collection_chest", "tool_rack",
            "storage_chest", "floor_object",
        }
        if placement in fixture_types and matching_buildings:
            def fixture_score(position):
                building = next(
                    item for item in matching_buildings
                    if (item.bounds[0] < position[0] < item.bounds[2]
                        and item.bounds[1] < position[1] < item.bounds[3]))
                left, top, right, bottom = building.bounds
                wall_distance = min(
                    position[0] - left, right - position[0],
                    position[1] - top, bottom - position[1])
                door_distance = (
                    abs(position[0] - building.door[0])
                    + abs(position[1] - building.door[1]))
                return (wall_distance, -door_distance, position[1], position[0])
            candidates.sort(key=fixture_score)
        elif placement in {"structural", "stone_display", "floor_object"}:
            candidates.sort(key=lambda item: (
                item in roads, item[1], item[0]))
        return candidates

    def _next_evidence_position(
            self, candidates: list[tuple[int, int]],
            occupied: set[tuple[int, int]],
            protected: set[tuple[int, int]],
            blocking_entities: set[tuple[int, int]],
            required_doors: set[tuple[int, int]],
            interaction_targets: set[tuple[int, int]], start_index: int,
            blocks_movement: bool, tiles: list[int],
            profile: SettlementMapProfile,
            player_start: tuple[int, int]) -> tuple[int, int]:
        ordered = list(candidates)
        fallback = [
            (x, y) for y in range(profile.height)
            for x in range(profile.width)
            if self._walkable(tiles, profile, (x, y))]
        for source in (ordered, fallback):
            if not source:
                continue
            for offset in range(len(source)):
                candidate = source[(start_index + offset) % len(source)]
                tile = tiles[candidate[1] * profile.width + candidate[0]]
                is_shelf = tile == TILE_SHELF
                if candidate in occupied or candidate in protected:
                    continue
                if not is_shelf and not self._walkable(
                        tiles, profile, candidate):
                    continue
                trial_blocking = set(blocking_entities)
                if blocks_movement and not is_shelf:
                    trial_blocking.add(candidate)
                reached = self._reachable_from(
                    tiles, profile, player_start, trial_blocking)
                if not required_doors <= reached:
                    continue
                if not all(any(
                    (target[0] + dx, target[1] + dy) in reached
                    for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)))
                    for target in interaction_targets | {candidate}):
                    continue
                return candidate
        raise RuntimeError("local map has no reachable evidence position")

    def _reachable_from(
            self, tiles: list[int], profile: SettlementMapProfile,
            start: tuple[int, int], extra_blocking: set[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        queue = deque([start])
        reached = {start}
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                neighbor = (x + dx, y + dy)
                if (neighbor in reached or neighbor in extra_blocking
                        or not self._walkable(tiles, profile, neighbor)):
                    continue
                reached.add(neighbor)
                queue.append(neighbor)
        return reached

    def _walkable_near(self, tiles: list[int], profile: SettlementMapProfile,
                       center: tuple[int, int], radius: int) -> list[tuple[int, int]]:
        cx, cy = center
        positions = []
        for distance in range(radius + 1):
            for y in range(max(0, cy - distance), min(profile.height, cy + distance + 1)):
                for x in range(max(0, cx - distance), min(profile.width, cx + distance + 1)):
                    if abs(x - cx) + abs(y - cy) != distance:
                        continue
                    if self._walkable(tiles, profile, (x, y)):
                        positions.append((x, y))
        return positions

    def _npc_candidates(self, tiles: list[int], roads: set[tuple[int, int]],
                        occupied: set[tuple[int, int]],
                        profile: SettlementMapProfile) -> list[tuple[int, int]]:
        candidates = [
            item for item in sorted(roads, key=lambda value: (
                abs(value[0] - profile.hub[0]) + abs(value[1] - profile.hub[1]),
                value[1], value[0]))
            if item not in occupied and self._walkable(tiles, profile, item)]
        return candidates or self._walkable_near(
            tiles, profile, profile.hub, max(profile.width, profile.height))

    def _residents(self, world, settlement,
                   occupied: set[tuple[int, int]],
                   candidates: list[tuple[int, int]], tiles: list[int],
                   profile: SettlementMapProfile) -> list[LocalMapEntity]:
        size_bonus = {"village": 0, "town": 3, "city": 6}.get(
            settlement.size, 0)
        count = min(14, 6 + settlement.population // 250 + size_bonus)
        used_names = {person.name for person in world.persons.values()}
        chatter_offset = self._stable_int(
            str(world.seed), settlement.id, "daily_chatter") % len(DAILY_CHATTER)
        residents = []
        for index in range(count):
            position = self._next_walkable_free(
                candidates, occupied, index, tiles, profile)
            occupied.add(position)
            seed = self._stable_int(
                str(world.seed), settlement.id, "resident", str(index))
            name = generate_unique_name(seed, used_names, "ruler")
            occupation = OCCUPATIONS[seed % len(OCCUPATIONS)]
            residents.append(LocalMapEntity(
                id=f"resident_{settlement.id}_{index + 1:02d}",
                kind="resident", x=position[0], y=position[1],
                name=name, subtype="person", role=occupation[0],
                role_name=occupation[1], state="daily_routine",
                zone="聚落街区",
                description_cn=(
                    f"一位住在{settlement.name}的{occupation[1]}。{occupation[2]}"),
                dialogue_cn=DAILY_CHATTER[
                    (chatter_offset + index) % len(DAILY_CHATTER)],
            ))
        return residents

    def _ruin_survivors(self, world, settlement,
                        occupied: set[tuple[int, int]],
                        candidates: list[tuple[int, int]], tiles: list[int],
                        profile: SettlementMapProfile,
                        informant_person_ids: set[str]) -> list[LocalMapEntity]:
        named = sorted((
            person for person in world.persons.values()
            if person.alive
            and person.current_location_id == settlement.id
            and person.mobility_status == "ruin_survivor"
            and person.id not in informant_person_ids
        ), key=lambda person: person.id)
        survivors = []
        for index, person in enumerate(named):
            position = self._next_walkable_free(
                candidates, occupied, index, tiles, profile)
            occupied.add(position)
            survivors.append(LocalMapEntity(
                id=person.id,
                kind="resident",
                x=position[0],
                y=position[1],
                name=person.name,
                subtype="person",
                role=person.roles[0] if person.roles else "survivor",
                role_name="废墟幸存者",
                state="ruin_survivor",
                zone="废墟幸存者营地",
                description_cn=(
                    f"一位在{settlement.name}毁灭后仍留在附近的幸存者。"),
                dialogue_cn="我们在残墙外搭起住处，只在白天进入废墟寻找还能使用的东西。",
            ))

        generic_count = min(4, settlement.population // 8)
        used_names = {person.name for person in world.persons.values()}
        for index in range(generic_count):
            position = self._next_walkable_free(
                candidates, occupied, len(named) + index, tiles, profile)
            occupied.add(position)
            name = generate_unique_name(
                self._stable_int(
                    str(world.seed), settlement.id, "ruin_survivor",
                    str(index)),
                used_names,
                "ruler",
            )
            used_names.add(name)
            survivors.append(LocalMapEntity(
                id=f"ruin_survivor_{settlement.id}_{index + 1:02d}",
                kind="resident",
                x=position[0],
                y=position[1],
                name=name,
                subtype="person",
                role="survivor",
                role_name="幸存居民",
                state="ruin_survivor",
                zone="废墟幸存者营地",
                description_cn="一位住在废墟边缘临时营地中的幸存居民。",
                dialogue_cn="多数人已经离开，留下的人轮流看守营地和辨认废墟中的旧物。",
            ))
        return survivors

    def _player_start(self, tiles: list[int], roads: set[tuple[int, int]],
                      profile: SettlementMapProfile,
                      occupied: set[tuple[int, int]]) -> tuple[int, int]:
        preferred = self._entrance_point(profile, profile.entrances[0], 0, "start")
        candidates = sorted(roads, key=lambda item: (
            abs(item[0] - preferred[0]) + abs(item[1] - preferred[1]),
            item[1], item[0]))
        return self._next_walkable_free(
            candidates, occupied, 0, tiles, profile)

    def _ruin_damage(self, tiles: list[int], profile: SettlementMapProfile,
                     seed: int, settlement_id: str) -> None:
        for y in range(profile.height):
            for x in range(profile.width):
                index = y * profile.width + x
                tile = tiles[index]
                roll = self._stable_int(
                    str(seed), settlement_id, "ruin", str(x), str(y)) % 100
                if tile == TILE_WALL and roll < 30:
                    tiles[index] = TILE_RUBBLE
                elif tile in {TILE_FLOOR, TILE_HOME_FLOOR,
                              TILE_SERVICE_FLOOR} and roll < 11:
                    tiles[index] = TILE_RUBBLE
                elif tile in {
                        TILE_GRASS, TILE_SAND, TILE_TUNDRA, TILE_MARSH
                } and roll < 3:
                    tiles[index] = TILE_RUBBLE

    def _next_walkable_free(self, candidates: list[tuple[int, int]],
                            occupied: set[tuple[int, int]], start_index: int,
                            tiles: list[int], profile: SettlementMapProfile) -> tuple[int, int]:
        for offset in range(len(candidates)):
            candidate = candidates[(start_index + offset) % len(candidates)]
            if candidate not in occupied and self._walkable(
                    tiles, profile, candidate):
                return candidate
        for y in range(profile.height):
            for x in range(profile.width):
                candidate = (x, y)
                if candidate not in occupied and self._walkable(
                        tiles, profile, candidate):
                    return candidate
        raise RuntimeError("local map has no walkable position")

    @staticmethod
    def _walkable(tiles: list[int], profile: SettlementMapProfile,
                  position: tuple[int, int]) -> bool:
        x, y = position
        if x < 0 or y < 0 or x >= profile.width or y >= profile.height:
            return False
        return tiles[y * profile.width + x] not in BLOCKING_TILES

    @staticmethod
    def _set(tiles: list[int], profile: SettlementMapProfile,
             x: int, y: int, value: int) -> None:
        if 0 <= x < profile.width and 0 <= y < profile.height:
            tiles[y * profile.width + x] = value

    @staticmethod
    def _stable_int(*parts: str) -> int:
        payload = "|".join(parts).encode("utf-8")
        return int(hashlib.sha256(payload).hexdigest()[:8], 16)
