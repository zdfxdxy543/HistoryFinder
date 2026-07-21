"""Deterministic local tile maps for the playable investigation prototype."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from simulation.names import generate_unique_name


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

BLOCKING_TILES = {TILE_WALL, TILE_WATER, TILE_RUBBLE, TILE_SHELF, TILE_STALL}


SITE_ZONE = {
    "library_collection": "archive",
    "administrative_archive": "archive",
    "private_collection": "archive",
    "temple_repository": "hall",
    "merchant_archive": "market",
    "workshop_store": "workshop",
    "storehouse": "workshop",
    "monument_site": "monument",
    "field_site": "field",
}


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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "name": self.name,
            "subtype": self.subtype,
            "role": self.role,
            "role_name": self.role_name,
            "state": self.state,
            "material": self.material,
            "zone": self.zone,
            "description_cn": self.description_cn,
            "dialogue_cn": self.dialogue_cn,
        }


@dataclass(frozen=True)
class LocalBuilding:
    id: str
    name: str
    building_type: str
    bounds: tuple[int, int, int, int]
    door: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "building_type": self.building_type,
            "bounds": list(self.bounds),
            "door": {"x": self.door[0], "y": self.door[1]},
        }


class LocalMapBuilder:
    width = 60
    height = 40

    def build(self, world, settlement) -> dict:
        tiles = [TILE_GRASS] * (self.width * self.height)
        self._biome_edge(tiles, settlement.biome)
        self._roads(tiles)
        buildings = self._buildings_for(settlement)
        for building in buildings:
            self._paint_building(tiles, building)
        self._market(tiles)
        self._set(tiles, 41, 24, TILE_WATER)

        evidence = sorted(
            world.get_all_visible_evidence(settlement.id),
            key=lambda item: (item.container_id or "", item.id),
        )[:14]
        informants = world.get_available_informants(settlement.id)
        player_start = (19, 34)
        occupied = {player_start}
        entities: list[LocalMapEntity] = []

        zone_indexes: dict[str, int] = {}
        for item in evidence:
            site = world.storage_sites.get(item.container_id)
            zone = SITE_ZONE.get(
                site.site_type if site is not None else "", "field")
            candidates = self._zone_candidates(zone)
            index = zone_indexes.get(zone, 0)
            position = self._next_free(candidates, occupied, index)
            zone_indexes[zone] = index + 1
            occupied.add(position)
            entities.append(LocalMapEntity(
                id=item.id,
                kind="evidence",
                x=position[0],
                y=position[1],
                name=item.physical_features.get(
                    "display_name", item.subtype.replace("_", " ")),
                subtype=item.evidence_type,
                state=item.state,
                material=item.material,
                zone=(site.name if site is not None else "露天调查区"),
            ))

        npc_candidates = [
            (17, 5), (20, 8), (38, 6), (41, 9), (10, 14),
            (27, 14), (37, 14), (43, 14), (17, 21), (20, 24),
            (38, 21), (42, 22),
        ]
        for index, informant in enumerate(informants):
            person = world.persons.get(informant.person_id)
            if person is None:
                continue
            position = self._next_free(npc_candidates, occupied, index)
            occupied.add(position)
            entities.append(LocalMapEntity(
                id=informant.id,
                kind="informant",
                x=position[0],
                y=position[1],
                name=person.name,
                subtype="person",
                role=informant.role,
                zone="聚落公共区域",
            ))

        entities.extend(self._residents(world, settlement, occupied))

        return {
            "schema_version": 2,
            "width": self.width,
            "height": self.height,
            "tiles": tiles,
            "blocking_tiles": sorted(BLOCKING_TILES),
            "player_start": {"x": player_start[0], "y": player_start[1]},
            "entities": [item.to_dict() for item in entities],
            "buildings": [item.to_dict() for item in buildings] + [{
                "id": "well",
                "name": "公共水井",
                "building_type": "well",
                "bounds": [41, 24, 41, 24],
                "door": {"x": 41, "y": 25},
            }],
            "zones": [
                {"id": "archive", "name": "档案馆", "bounds": [2, 2, 15, 12]},
                {"id": "workshop", "name": "工坊", "bounds": [22, 2, 35, 12]},
                {"id": "residential", "name": "东街住区", "bounds": [43, 2, 58, 13]},
                {"id": "hall", "name": "公共厅堂", "bounds": [2, 18, 15, 26]},
                {"id": "monument", "name": "纪念地", "bounds": [22, 18, 28, 26]},
                {"id": "market", "name": "集市", "bounds": [30, 18, 37, 26]},
                {"id": "services", "name": "生活街", "bounds": [43, 18, 58, 25]},
                {"id": "field", "name": "田地与调查区", "bounds": [22, 30, 37, 38]},
            ],
        }

    def _buildings_for(self, settlement) -> list[LocalBuilding]:
        buildings = [
            LocalBuilding("archive", "档案馆", "archive", (2, 2, 15, 12), (8, 12)),
            LocalBuilding("workshop", "工坊", "workshop", (22, 2, 35, 12), (28, 12)),
            LocalBuilding("hall", "公共厅堂", "hall", (2, 18, 15, 26), (8, 26)),
            LocalBuilding("inn", "旅人客栈", "inn", (43, 18, 49, 25), (43, 22)),
            LocalBuilding("bakery", "街角面包房", "bakery", (52, 18, 58, 25), (52, 22)),
            LocalBuilding("granary", "公共粮仓", "granary", (2, 30, 8, 38), (5, 30)),
        ]
        home_plots = [
            ((43, 2, 49, 7), (46, 7)),
            ((52, 2, 58, 7), (55, 7)),
            ((43, 9, 49, 13), (46, 13)),
            ((52, 9, 58, 13), (55, 13)),
            ((10, 30, 16, 38), (13, 30)),
            ((43, 30, 49, 38), (46, 30)),
            ((52, 30, 58, 38), (55, 30)),
        ]
        target = {"village": 5, "town": 6, "city": 7}.get(
            settlement.size, 5)
        for index, (bounds, door) in enumerate(home_plots[:target], start=1):
            buildings.append(LocalBuilding(
                f"home_{index:02d}", f"民居 {index}", "home", bounds, door))
        return buildings

    def _paint_building(self, tiles: list[int], building: LocalBuilding) -> None:
        floor = (
            TILE_HOME_FLOOR if building.building_type == "home"
            else TILE_SERVICE_FLOOR if building.building_type in {
                "inn", "bakery", "granary"}
            else TILE_FLOOR
        )
        left, top, right, bottom = building.bounds
        self._building(
            tiles, left, top, right, bottom, building.door[0],
            building.door[1], floor)
        if building.building_type == "archive":
            for y in range(4, 11):
                self._set(tiles, 4, y, TILE_SHELF)
                self._set(tiles, 13, y, TILE_SHELF)
        elif building.building_type == "workshop":
            for x in range(24, 34, 3):
                self._set(tiles, x, 5, TILE_STALL)
        elif building.building_type == "granary":
            for y in (32, 35):
                self._set(tiles, 4, y, TILE_STALL)
                self._set(tiles, 6, y, TILE_STALL)

    def _roads(self, tiles: list[int]) -> None:
        for x in range(self.width):
            for y in (14, 15, 27, 28):
                self._set(tiles, x, y, TILE_ROAD)
        for y in range(self.height):
            for x in (18, 19, 39, 40):
                self._set(tiles, x, y, TILE_ROAD)
        for x in range(8, 56):
            self._set(tiles, x, 16, TILE_ROAD)
        for y in range(12, 31):
            for x in (8, 28, 46, 55):
                self._set(tiles, x, y, TILE_ROAD)

    def _building(self, tiles: list[int], left: int, top: int,
                  right: int, bottom: int, door_x: int, door_y: int,
                  floor_tile: int = TILE_FLOOR) -> None:
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                edge = x in {left, right} or y in {top, bottom}
                self._set(tiles, x, y, TILE_WALL if edge else floor_tile)
        self._set(tiles, door_x, door_y, floor_tile)

    def _market(self, tiles: list[int]) -> None:
        for x, y in ((31, 20), (35, 20), (31, 24), (35, 24)):
            self._set(tiles, x, y, TILE_STALL)

    def _residents(self, world, settlement,
                   occupied: set[tuple[int, int]]) -> list[LocalMapEntity]:
        candidates = [
            (42, 5), (50, 5), (42, 11), (50, 11), (44, 14),
            (54, 14), (16, 17), (21, 17), (29, 17), (41, 19),
            (50, 20), (59, 22), (9, 27), (22, 27), (34, 27),
            (44, 27), (54, 27), (9, 33), (17, 33), (21, 34),
            (38, 34), (42, 34), (50, 34), (59, 34),
        ]
        size_bonus = {"village": 0, "town": 3, "city": 6}.get(
            settlement.size, 0)
        count = min(14, 6 + settlement.population // 250 + size_bonus)
        used_names = {person.name for person in world.persons.values()}
        residents = []
        chatter_offset = self._stable_int(
            str(world.seed), settlement.id, "daily_chatter") % len(DAILY_CHATTER)
        for index in range(count):
            position = self._next_free(candidates, occupied, index)
            occupied.add(position)
            seed = self._stable_int(
                str(world.seed), settlement.id, "resident", str(index))
            name = generate_unique_name(seed, used_names, "ruler")
            occupation = OCCUPATIONS[seed % len(OCCUPATIONS)]
            chatter = DAILY_CHATTER[
                (chatter_offset + index) % len(DAILY_CHATTER)]
            residents.append(LocalMapEntity(
                id=f"resident_{settlement.id}_{index + 1:02d}",
                kind="resident",
                x=position[0],
                y=position[1],
                name=name,
                subtype="person",
                role=occupation[0],
                role_name=occupation[1],
                state="daily_routine",
                zone=self._resident_zone(position),
                description_cn=f"一位住在{settlement.name}的{occupation[1]}。{occupation[2]}",
                dialogue_cn=chatter,
            ))
        return residents

    @staticmethod
    def _resident_zone(position: tuple[int, int]) -> str:
        x, y = position
        if x >= 42 and y <= 16:
            return "东街住区"
        if x >= 41 and 17 <= y <= 26:
            return "生活街"
        if 30 <= x <= 38 and 17 <= y <= 26:
            return "集市"
        if y >= 29:
            return "南部街区"
        return "聚落公共区域"

    def _biome_edge(self, tiles: list[int], biome: str) -> None:
        if biome in {"river_valley", "forest"}:
            for y in range(self.height):
                width = 2 + (self._stable_int(biome, str(y)) % 2)
                for x in range(width):
                    self._set(tiles, x, y, TILE_WATER)
        elif biome in {"mountain", "highland"}:
            for y in range(0, self.height, 3):
                self._set(tiles, 58, y, TILE_RUBBLE)
                self._set(tiles, 59, y, TILE_RUBBLE)

    def _zone_candidates(self, zone: str) -> list[tuple[int, int]]:
        candidates = {
            "archive": [
                (6, 4), (8, 4), (10, 4), (6, 7), (8, 7), (10, 7),
                (6, 10), (8, 10), (10, 10), (12, 7),
            ],
            "workshop": [
                (25, 7), (28, 7), (31, 7), (34, 7), (25, 10), (31, 10),
            ],
            "hall": [(5, 20), (8, 20), (11, 20), (13, 23), (8, 24)],
            "market": [(30, 19), (33, 22), (37, 20), (30, 25), (37, 25)],
            "monument": [(22, 20), (25, 20), (28, 20), (23, 24), (27, 24)],
            "field": [(23, 31), (27, 33), (31, 31), (35, 33), (24, 37), (34, 37)],
        }
        return candidates.get(zone, candidates["field"])

    @staticmethod
    def _next_free(candidates: list[tuple[int, int]], occupied: set,
                   start_index: int) -> tuple[int, int]:
        for offset in range(len(candidates)):
            candidate = candidates[(start_index + offset) % len(candidates)]
            if candidate not in occupied:
                return candidate
        x, y = candidates[start_index % len(candidates)]
        return x + start_index // len(candidates), y

    def _set(self, tiles: list[int], x: int, y: int, value: int) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            tiles[y * self.width + x] = value

    @staticmethod
    def _stable_int(*parts: str) -> int:
        payload = "|".join(parts).encode("utf-8")
        return int(hashlib.sha256(payload).hexdigest()[:8], 16)
