"""Lazy deterministic maps for world cells without settlements."""

from __future__ import annotations

import hashlib
import math
from collections import deque

from simulation.religion import primary_religion
from simulation.historical_sites import site_signature

from game.local_map import (
    BLOCKING_TILES,
    PLACEMENT_PROFILES,
    TILE_BRIDGE,
    TILE_FOREST,
    TILE_FLOOR,
    TILE_FENCE,
    TILE_GRASS,
    TILE_MARSH,
    TILE_ROAD,
    TILE_ROCK,
    TILE_RUBBLE,
    TILE_SAND,
    TILE_TUNDRA,
    TILE_WATER,
    TILE_WALL,
    build_evidence_targets,
    paint_watercourse,
)


CELL_MAP_WIDTH = 80
CELL_MAP_HEIGHT = 56


BIOME_BASE_TILE = {
    "ocean": TILE_WATER,
    "lake": TILE_WATER,
    "river": TILE_GRASS,
    "mountain": TILE_GRASS,
    "highland": TILE_GRASS,
    "forest": TILE_GRASS,
    "desert": TILE_SAND,
    "scrubland": TILE_SAND,
    "tundra": TILE_TUNDRA,
    "river_valley": TILE_GRASS,
    "grassland": TILE_GRASS,
    "plains": TILE_GRASS,
}


LANDSCAPE_NAMES = {
    "ocean": "海洋",
    "lake": "湖泊",
    "river": "河道",
    "mountain": "山脉",
    "highland": "高地",
    "forest": "森林",
    "desert": "荒漠",
    "scrubland": "灌木荒地",
    "tundra": "苔原",
    "river_valley": "河谷",
    "grassland": "草原",
    "plains": "平原",
}

DECORATION_PALETTES = {
    "forest": ("fern", "sapling", "fallen_branch", "mushroom", "leaf_patch"),
    "river": ("reeds", "river_stone", "driftwood", "water_grass"),
    "river_valley": ("reeds", "wildflowers", "river_stone", "willow_shoot"),
    "mountain": ("stone_cluster", "alpine_shrub", "dead_branch", "lichen"),
    "highland": ("stone_cluster", "heather", "alpine_shrub", "dry_grass"),
    "desert": ("dry_shrub", "desert_grass", "bleached_branch", "small_stone"),
    "scrubland": ("dry_shrub", "thorn_bush", "dry_grass", "small_stone"),
    "tundra": ("dwarf_shrub", "lichen", "pale_grass", "small_stone"),
    "grassland": ("grass_tuft", "wildflowers", "small_stone", "low_shrub"),
    "plains": ("grass_tuft", "wildflowers", "low_shrub", "fallen_branch"),
}

ROADSIDE_TRACES = (
    ("cart_ruts", "旧车辙", "两道反复碾压形成的车辙已经积水，边缘还能看到牲畜蹄印。"),
    ("broken_wheel", "折断的车轮", "半只车轮被推到路旁，断口和临时拆下的铁箍说明它曾在这里损坏。"),
    ("old_fire_ring", "旧火塘", "一圈发黑石块围着冷灰，附近散落着削尖木棍和烧裂的陶片。"),
    ("discarded_pack", "遗落的货物包装", "破麻布和断绳沾满尘土，原先捆扎的货物已经不见。"),
)

REMOTE_TRACES = (
    ("cut_stumps", "伐木痕迹", "几处树桩留下不同深浅的斧痕，拖拽木料形成的浅沟通向远处。"),
    ("stone_cairn", "人工石堆", "大小相近的石块被刻意垒起，顶部压着一根褪色布条。"),
    ("hunter_blind", "废弃猎棚", "树枝和草绳搭成的低矮掩体已经塌了一半，地面仍留有旧脚印。"),
    ("charcoal_patch", "烧炭痕迹", "土壤呈深黑色，碎木炭和被削平的地面说明这里曾有人烧炭。"),
)

WILDLIFE_BY_BIOME = {
    "forest": (("deer", "林鹿"), ("hare", "野兔")),
    "river": (("heron", "苍鹭"), ("waterfowl", "水鸟")),
    "river_valley": (("heron", "苍鹭"), ("hare", "野兔")),
    "mountain": (("mountain_goat", "岩羊"), ("ptarmigan", "山鹑")),
    "highland": (("mountain_goat", "岩羊"), ("fox", "狐狸")),
    "desert": (("lizard", "沙蜥"), ("fox", "荒漠狐")),
    "scrubland": (("lizard", "蜥蜴"), ("hare", "野兔")),
    "tundra": (("ptarmigan", "雷鸟"), ("hare", "雪兔")),
    "grassland": (("deer", "草原鹿"), ("hare", "野兔")),
    "plains": (("deer", "小鹿"), ("hare", "野兔")),
}


def cell_key(x: int, y: int) -> str:
    return f"{x},{y}"


def route_signature(world, x: int, y: int) -> str:
    road_values = sorted(
        (segment.id, segment.revision, segment.status)
        for segment in world.get_road_segments_at(x, y)
    )
    signpost_values = sorted(
        (signpost.id, signpost.revision, signpost.condition)
        for signpost in world.get_signposts_at(x, y)
    )
    routes = "|".join(f"road:{key}:{revision}:{status}"
                      for key, revision, status in road_values)
    signposts = "|".join(f"signpost:{key}:{revision}:{condition}"
                         for key, revision, condition in signpost_values)
    return "|".join(item for item in (routes, signposts) if item)


def edge_portal(road_id: str, first: tuple[int, int],
                second: tuple[int, int], width: int,
                height: int) -> tuple[int, int]:
    low, high = sorted((first, second))
    digest = hashlib.sha256(
        f"road-edge|{low[0]},{low[1]}|{high[0]},{high[1]}".encode(
            "utf-8")
    ).digest()
    fraction = (int.from_bytes(digest[:4], "big") % 7001 + 1500) / 10000.0
    dx, dy = second[0] - first[0], second[1] - first[1]
    if dx > 0:
        return width - 1, round(fraction * (height - 1))
    if dx < 0:
        return 0, round(fraction * (height - 1))
    if dy > 0:
        return round(fraction * (width - 1)), height - 1
    return round(fraction * (width - 1)), 0


def route_portals(world, x: int, y: int, width: int,
                  height: int) -> list[tuple[str, list[tuple[int, int]]]]:
    current = (x, y)
    result = []
    for segment in world.get_road_segments_at(x, y):
        if segment.status == "ruined":
            continue
        neighbor = (segment.cell_b if current == segment.cell_a
                    else segment.cell_a)
        result.append((segment.id, [
            edge_portal(segment.id, current, neighbor, width, height)]))
    return result


def paint_trade_routes(tiles: list[int], world, x: int, y: int,
                       width: int, height: int,
                       hub: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    roads: set[tuple[int, int]] = set()
    entries = route_portals(world, x, y, width, height)
    if not entries:
        return roads
    portals = [portals[0] for _, portals in entries]
    statuses = {segment_id: world.road_segments[segment_id].status
                for segment_id, _ in entries}
    target = hub or (width // 2, height // 2)
    entry_statuses = {statuses[key] for key, _ in entries}
    if len(portals) == 2 and hub is None and len(entry_statuses) == 1:
        shared_status = next(iter(entry_statuses))
        _carve(tiles, width, height, portals[0], portals[1], roads,
               _stable_int(*(key for key, _ in entries)), shared_status)
        return roads
    for (segment_id, _), portal in zip(entries, portals):
        _carve(tiles, width, height, portal, target, roads,
               _stable_int(segment_id, cell_key(x, y)),
               statuses[segment_id])
    return roads


class WorldCellMapBuilder:
    def build(self, world, x: int, y: int) -> dict:
        geography = world.geography
        biome = str(geography.biomes[y, x])
        width, height = CELL_MAP_WIDTH, CELL_MAP_HEIGHT
        base = BIOME_BASE_TILE.get(biome, TILE_GRASS)
        tiles = [base] * (width * height)
        roads: set[tuple[int, int]] = set()
        if biome not in {"ocean", "lake"}:
            self._paint_land(tiles, world.seed, x, y, biome, width, height)
            self._paint_boundary_transitions(
                tiles, geography, x, y, width, height)
            self._paint_river(tiles, geography, x, y, width, height)
            roads = paint_trade_routes(tiles, world, x, y, width, height)

        site_buildings, site_zones, site_entities, site_reserved = \
            self._paint_historical_sites(
                world, x, y, tiles, roads, width, height)
        entities = self._wilderness_entities(
            world, x, y, tiles, roads, width, height, site_reserved)
        entities.extend(site_entities)
        entities.extend(self._wilderness_evidence_entities(
            world, x, y, tiles, site_reserved, site_buildings, entities,
            width, height))
        decorations = self._wilderness_decorations(
            world.seed, x, y, biome, tiles, roads, entities, width, height)

        feature_types = {
            "river": {"river"}, "lake": {"lake"},
            "mountain": {"mountain"}, "highland": {"mountain"},
            "plains": {"plains"}, "grassland": {"plains"},
            "forest": {"forest"}, "desert": {"desert"},
            "scrubland": {"desert"}, "tundra": {"tundra"},
            "river_valley": {"river", "plains"},
        }.get(biome, set())
        features = geography.get_features_at(x, y)
        if feature_types:
            features = [
                feature for feature in features
                if feature.feature_type in feature_types]
        if not features and feature_types:
            features = geography.nearest_features(
                x, y, feature_types, max_distance=3.0, limit=2)
        feature_names = [feature.name for feature in features]

        start = self._nearest_walkable(
            tiles, width, height, (width // 2, height // 2))
        return {
            "schema_version": 10,
            "site_type": "wilderness",
            "cell": {"x": x, "y": y},
            "width": width,
            "height": height,
            "profile": {
                "layout_type": "wilderness",
                "layout_name": "野外",
                "water_axis": "none",
                "water_side": "none",
                "hub": {"x": width // 2, "y": height // 2},
                "entrances": ["north", "south", "east", "west"],
                "landscape_type": biome,
                "landscape_name": (
                    feature_names[0] if feature_names
                    else LANDSCAPE_NAMES.get(biome, biome)),
                "feature_names": feature_names,
            },
            "tiles": tiles,
            "blocking_tiles": sorted(BLOCKING_TILES),
            "player_start": {"x": start[0], "y": start[1]},
            "entities": entities,
            "decorations": decorations,
            "discovered_evidence": [],
            "buildings": site_buildings,
            "zones": site_zones,
            "route_signature": route_signature(world, x, y),
            "historical_site_signature": site_signature(
                world.get_historical_sites_at(x, y)),
        }

    def _paint_historical_sites(
            self, world, x: int, y: int, tiles: list[int],
            roads: set[tuple[int, int]], width: int, height: int,
            ) -> tuple[list[dict], list[dict], list[dict],
                       set[tuple[int, int]]]:
        layouts = {
            "roadside_inn": (18, 14, "商旅驿站"),
            "tollhouse": (14, 10, "道路关卡"),
            "farmstead": (22, 16, "农庄院落"),
            "mine": (20, 16, "矿场建筑群"),
            "logging_camp": (20, 15, "林场建筑群"),
            "watchtower": (14, 14, "哨塔营院"),
            "battlefield_ruins": (28, 20, "战场遗址"),
            "burned_waystation": (18, 14, "焚毁驿站"),
            "disaster_ruins": (24, 18, "灾变遗址"),
            "abandoned_hamlet": (28, 20, "废弃村落"),
            "ruined_outpost": (18, 16, "旧营垒"),
            "cemetery": (6, 8, "墓园"),
            "abandoned_cemetery": (6, 8, "废弃墓园"),
        }
        buildings: list[dict] = []
        zones: list[dict] = []
        entities: list[dict] = []
        reserved: set[tuple[int, int]] = set()
        for site_index, site in enumerate(world.get_historical_sites_at(x, y)):
            if site.site_type not in layouts:
                continue
            site_width, site_height, zone_name = layouts[site.site_type]
            seed = _stable_int(
                str(world.seed), site.id, cell_key(x, y), "footprint")
            is_cemetery = site.site_type in {
                "cemetery", "abandoned_cemetery"}
            left = 5 + seed % max(1, width - site_width - 10)
            top = 5 + (seed // 101) % max(1, height - site_height - 10)
            candidates = []
            for candidate_top in range(3, height - site_height - 2):
                for candidate_left in range(3, width - site_width - 2):
                        candidate = {
                            (px, py)
                            for py in range(
                                candidate_top, candidate_top + site_height)
                            for px in range(
                                candidate_left, candidate_left + site_width)
                        }
                        clearance = {
                            (px, py)
                            for cell_x, cell_y in candidate
                            for px in range(max(0, cell_x - 1),
                                            min(width, cell_x + 2))
                            for py in range(max(0, cell_y - 1),
                                            min(height, cell_y + 2))
                        }
                        road_conflict = (
                            clearance & roads if is_cemetery
                            else candidate & roads)
                        if candidate & reserved or road_conflict:
                            continue
                        road_distance = min((
                            abs(candidate_left + site_width // 2 - road_x)
                            + abs(candidate_top + site_height // 2 - road_y)
                            for road_x, road_y in roads
                        ), default=0)
                        rank = _stable_int(
                            str(seed), str(candidate_left), str(candidate_top))
                        candidates.append((
                            road_distance if site.route_id else 0,
                            rank, candidate_left, candidate_top))
            if candidates:
                _, _, left, top = min(candidates)
            right = min(width - 4, left + site_width - 1)
            bottom = min(height - 4, top + site_height - 1)
            footprint = {
                (px, py) for py in range(top, bottom + 1)
                for px in range(left, right + 1)
            }
            if footprint & reserved:
                shift = min(8, max(0, width - right - 4))
                left, right = left + shift, right + shift
                footprint = {
                    (px, py) for py in range(top, bottom + 1)
                    for px in range(left, right + 1)
                }
            reserved.update(footprint)
            ruined = site.state in {"ruined", "abandoned"}
            damaged = site.state == "damaged"
            target = min(roads, key=lambda item: (
                abs(item[0] - (left + right) // 2)
                + abs(item[1] - (top + bottom) // 2),
                item[1], item[0])) if roads else ((left + right) // 2, height - 1)
            center_x = (left + right) // 2
            center_y = (top + bottom) // 2
            if target[0] < left:
                door = (left, center_y)
            elif target[0] > right:
                door = (right, center_y)
            elif target[1] < top:
                door = (center_x, top)
            else:
                door = (center_x, bottom)
            floor = TILE_RUBBLE if ruined else TILE_FLOOR
            for py in range(top, bottom + 1):
                for px in range(left, right + 1):
                    edge = px in {left, right} or py in {top, bottom}
                    index = py * width + px
                    if edge and is_cemetery:
                        collapse = _stable_int(site.id, str(px), str(py)) % 9
                        tiles[index] = (
                            TILE_GRASS if (
                                ruined and collapse < 5
                                or damaged and collapse == 0)
                            else TILE_FENCE)
                    elif is_cemetery:
                        center_x = (left + right) // 2
                        tiles[index] = (
                            TILE_FLOOR if px == center_x else TILE_GRASS)
                    elif not is_cemetery and ruined and _stable_int(
                            site.id, "debris", str(px), str(py)) % 17 == 0:
                        tiles[index] = TILE_RUBBLE
            if not is_cemetery:
                self._paint_site_variant(
                    tiles, width, height, site, (left, top, right, bottom),
                    seed, ruined, damaged)
            tiles[door[1] * width + door[0]] = TILE_FLOOR
            reserved.discard(door)
            if door[0] == left:
                road_start = (max(0, left - 2), door[1])
            elif door[0] == right:
                road_start = (min(width - 1, right + 1), door[1])
            elif door[1] == top:
                road_start = (door[0], max(0, top - 1))
            else:
                road_start = (door[0], min(height - 1, bottom + 1))
            _carve(tiles, width, height, road_start, target, roads, seed)
            condition = (
                "ruined" if ruined else "damaged" if damaged else "intact")
            fragment = site.occupied_cells.index((x, y)) + 1
            building_name = (site.name if len(site.occupied_cells) == 1
                             else f"{site.name}第{fragment}片区")
            buildings.append({
                "id": f"{site.id}:{x},{y}",
                "name": building_name,
                "building_type": site.site_type,
                "bounds": [left, top, right, bottom],
                "door": {"x": door[0], "y": door[1]},
                "condition": condition,
                "infrastructure_type": "historical_site",
                "infrastructure_level": site.condition,
                "historical_site_id": site.id,
                "layout_variant": int(seed % 4),
            })
            zones.append({
                "id": f"zone_{site.id}_{x}_{y}",
                "name": zone_name,
                "zone_type": site.site_type,
                "bounds": [left, top, right, bottom],
                "historical_site_id": site.id,
            })
        return buildings, zones, entities, reserved

    @staticmethod
    def _paint_site_variant(
            tiles: list[int], width: int, height: int, site,
            bounds: tuple[int, int, int, int], seed: int,
            ruined: bool, damaged: bool) -> None:
        left, top, right, bottom = bounds
        open_types = {
            "farmstead", "logging_camp", "battlefield_ruins",
            "disaster_ruins", "abandoned_hamlet"}
        fortified = site.site_type in {"watchtower", "ruined_outpost"}
        structure_count = 2 + seed % 3
        for structure_index in range(structure_count):
            value = _stable_int(site.id, str(structure_index), str(seed))
            structure_width = 4 + value % min(6, max(1, right - left - 4))
            structure_height = 4 + (value // 17) % min(
                5, max(1, bottom - top - 4))
            structure_left = left + 2 + (value // 37) % max(
                1, right - left - structure_width - 2)
            structure_top = top + 2 + (value // 71) % max(
                1, bottom - top - structure_height - 2)
            structure_right = min(right - 1,
                                  structure_left + structure_width - 1)
            structure_bottom = min(bottom - 1,
                                   structure_top + structure_height - 1)
            doorway = ((structure_left + structure_right) // 2,
                       structure_bottom)
            for py in range(structure_top, structure_bottom + 1):
                for px in range(structure_left, structure_right + 1):
                    edge = px in {structure_left, structure_right} or py in {
                        structure_top, structure_bottom}
                    index = py * width + px
                    if not edge:
                        if not ruined:
                            tiles[index] = TILE_FLOOR
                        continue
                    fragment = _stable_int(
                        site.id, str(structure_index), str(px), str(py)) % 7
                    if ruined and fragment < 4:
                        tiles[index] = TILE_RUBBLE if fragment == 0 else TILE_GRASS
                    elif damaged and fragment == 0:
                        tiles[index] = TILE_RUBBLE
                    elif site.site_type in open_types and fragment % 3 == 0:
                        tiles[index] = TILE_FENCE
                    else:
                        tiles[index] = TILE_WALL
            tiles[doorway[1] * width + doorway[0]] = TILE_FLOOR
        if site.site_type in open_types or fortified:
            boundary_tile = TILE_WALL if fortified else TILE_FENCE
            variant = seed % 4
            segments = (
                ((left, top, right - 2, top),
                 (left, top, left, bottom - 3)),
                ((left + 2, bottom, right, bottom),
                 (right, top + 3, right, bottom)),
                ((left, top, left + (right - left) // 2, top),
                 (right - (right - left) // 3, bottom, right, bottom)),
                ((left, top + 2, left, bottom - 2),
                 (right, top + 2, right, bottom - 2)),
            )[variant]
            for x1, y1, x2, y2 in segments:
                for px in range(min(x1, x2), max(x1, x2) + 1):
                    for py in range(min(y1, y2), max(y1, y2) + 1):
                        if _stable_int(site.id, "boundary", str(px), str(py)) % 9:
                            tiles[py * width + px] = boundary_tile

    def _wilderness_evidence_entities(
            self, world, x: int, y: int, tiles: list[int],
            reserved: set[tuple[int, int]], buildings: list[dict],
            entities: list[dict],
            width: int, height: int) -> list[dict]:
        location_id = cell_key(x, y)
        targets = build_evidence_targets(
            world.evidence.values(), world.storage_sites, location_id)
        occupied = {(item["x"], item["y"]) for item in entities}
        candidates = [
            (px, py)
            for py in range(2, height - 2)
            for px in range(2, width - 2)
            if tiles[py * width + px] not in BLOCKING_TILES
            and (px, py) not in occupied
        ]
        candidates.sort(key=lambda item: (
            0 if item in reserved else 1,
            abs(item[0] - width // 2) + abs(item[1] - height // 2),
            item[1], item[0],
        ))
        burial_by_evidence = {
            burial.inscription_evidence_id: burial
            for burial in world.burials.values()
            if burial.inscription_evidence_id
        }
        bounds_by_site = {
            item["historical_site_id"]: item["bounds"]
            for item in buildings if item.get("historical_site_id")
        }
        site_by_evidence = {
            evidence_id: site.id
            for site in world.get_historical_sites_at(x, y)
            for evidence_id in site.evidence_ids
        }
        result = []
        for index, target in enumerate(targets):
            if not candidates:
                break
            seed = _stable_int(str(world.seed), location_id, target["id"])
            first = world.evidence[target["evidence_ids"][0]]
            burial = burial_by_evidence.get(first.id)
            historical_site_id = (
                burial.site_id if burial is not None
                else site_by_evidence.get(first.id, ""))
            site_candidates = []
            if historical_site_id in bounds_by_site:
                left, top, right, bottom = bounds_by_site[historical_site_id]
                center_x = (left + right) // 2
                site_candidates = [
                    item for item in candidates
                    if left < item[0] < right and top < item[1] < bottom
                    and (burial is None or item[0] != center_x)
                ]
            eligible = site_candidates or candidates
            position = eligible[seed % len(eligible)]
            candidates.remove(position)
            placement = target["placement_kind"]
            label, description, _, blocks = PLACEMENT_PROFILES[placement]
            if target["kind"] == "evidence":
                person = (
                    world.persons.get(burial.person_id)
                    if burial is not None else None)
                name = (f"{person.name}的墓碑" if person is not None
                        else first.physical_features.get(
                            "display_name", first.subtype.replace("_", " ")))
                subtype = first.subtype
                material = first.material
                state = first.state
            else:
                name = f"{label}"
                subtype = placement
                material = ""
                state = "weathered"
            result.append({
                "id": target["id"],
                "kind": target["kind"],
                "x": position[0], "y": position[1],
                "name": name,
                "subtype": subtype,
                "role": "public", "role_name": "可调查",
                "state": state, "material": material,
                "zone": "历史地点现场",
                "description_cn": description,
                "dialogue_cn": "",
                "accessibility": "public",
                "condition": "受损" if state != "intact" else "完好",
                "searched": False,
                "discovered_count": 0,
                "placement_kind": placement,
                "storage_site_id": target["storage_site_id"],
                "blocks_movement": blocks,
            })
            occupied.add(position)
        return result

    def _wilderness_entities(self, world, x: int, y: int,
                             tiles: list[int], roads: set[tuple[int, int]],
                             width: int, height: int,
                             reserved: set[tuple[int, int]] | None = None
                             ) -> list[dict]:
        entities = []
        occupied: set[tuple[int, int]] = set(reserved or ())
        current = (x, y)
        routes = [
            route for route in sorted(
                world.trade_routes.values(), key=lambda item: item.id)
            if route.status == "active" and current in route.path
        ]
        road_candidates = sorted(roads, key=lambda item: (
            abs(item[0] - width // 2) + abs(item[1] - height // 2),
            item[1], item[0],
        ))
        signposts = world.get_signposts_at(x, y)
        for signpost in signposts:
            anchor = (road_candidates[0] if road_candidates
                      else (width // 2, height // 2))
            sign_position = self._open_near(
                tiles, width, height, anchor, occupied)
            occupied.add(sign_position)
            direction_names = {
                "north": "北", "east": "东", "south": "南", "west": "西",
            }
            directions = [
                f"向{direction_names.get(board.direction, board.direction)}："
                f"{board.displayed_name}约{board.displayed_distance}格"
                for board in signpost.current_boards
            ]
            wear_data = {
                "light": ("轻度磨损", "牌面边缘被风沙磨圆，刻痕仍然清楚。"),
                "moderate": ("中度磨损", "木纹已经开裂，部分笔画被雨水晕开。"),
                "heavy": ("重度磨损", "牌角残缺，旧刻字和里程已有脱落。"),
            }
            wear_name, wear_description = wear_data.get(
                signpost.wear_level, wear_data["light"])
            repair = (signpost.repair_history[-1]
                      if signpost.repair_history else None)
            repair_names = {
                "iron_strap": "铁箍加固",
                "replacement_board": "补木修复",
                "rope_binding": "绳索捆扎",
                "fresh_paint": "重描箭头",
            }
            error_names = {
                "none": "修补准确",
                "misspelling": "疑似错字",
                "distance_error": "里程重写",
                "missing_character": "字符脱落",
                "illegible_text": "地名字迹模糊",
                "illegible_distance": "距离无法辨认",
            }
            repair_text = ""
            if repair is not None:
                repair_text = (
                    f"牌面留有{repair_names.get(repair.repair_type, repair.repair_type)}"
                    f"的痕迹，修于{repair.year}年。")
            abandoned_text = (
                f"这块路牌自{signpost.abandoned_year}年起无人维护。"
                if signpost.abandoned_year is not None else "")
            entities.append(_wilderness_entity(
                entity_id=signpost.id,
                kind="landmark",
                subtype="signpost",
                position=sign_position,
                name="道路指示牌",
                role="route_marker",
                role_name="路标",
                zone="旧道路" if signpost.abandoned_year is not None
                else "贸易道路",
                description=(
                    f"一根立于{signpost.built_year}年的木制路标。"
                    f"{wear_description}{repair_text}{abandoned_text}"
                    + "；".join(directions) + "。"),
                dialogue="；".join(directions),
                extra={
                    "signpost_id": signpost.id,
                    "built_year": signpost.built_year,
                    "builder_settlement_id": signpost.builder_settlement_id,
                    "route_ids": list(signpost.route_ids),
                    "condition": signpost.condition,
                    "wear_level": signpost.wear_level,
                    "wear_name": wear_name,
                    "repair_type": repair.repair_type if repair else "none",
                    "repair_name": (repair_names.get(
                        repair.repair_type, repair.repair_type)
                        if repair else "无修补痕迹"),
                    "repair_error_type": repair.error_type if repair else "none",
                    "repair_error_name": (error_names.get(
                        repair.error_type, repair.error_type)
                        if repair else "无修补错误"),
                    "abandoned_year": signpost.abandoned_year,
                    "original_boards": [
                        board.to_dict() for board in signpost.original_boards],
                    "current_boards": [
                        board.to_dict() for board in signpost.current_boards],
                    "repair_history": [
                        item.to_dict() for item in signpost.repair_history],
                },
            ))

        old_road_segments = [
            segment for segment in world.get_road_segments_at(x, y)
            if segment.status in {"overgrown", "ruined"}
        ]
        if old_road_segments:
            old_road_position = self._open_near(
                tiles, width, height,
                road_candidates[0] if road_candidates
                else (width // 2, height // 2),
                occupied,
            )
            occupied.add(old_road_position)
            ruined = all(
                segment.status == "ruined" for segment in old_road_segments)
            entities.append(_wilderness_entity(
                entity_id=f"old_road_{x}_{y}",
                kind="trace",
                subtype="road_remains" if ruined else "overgrown_road",
                position=old_road_position,
                name="道路遗迹" if ruined else "荒草旧路",
                role="travel_trace",
                role_name="旧道路",
                zone="荒野",
                description=(
                    "断续的铺路石和塌陷路基还保留着道路的走向。"
                    if ruined else
                    "荒草覆盖了大部分路面，零散车辙仍沿旧路延伸。"),
                extra={
                    "blocks_movement": False,
                    "road_segment_ids": [
                        segment.id for segment in old_road_segments],
                    "road_status": "ruined" if ruined else "overgrown",
                },
            ))

        # Opt-in adapter for pre-persistence integrations. Current World
        # instances always project their stored signposts above.
        if (getattr(world, "allow_legacy_transient_signposts", False)
                and not signposts and routes):
            sign_position = self._open_near(
                tiles, width, height,
                road_candidates[0] if road_candidates else (width // 2, height // 2),
                occupied,
            )
            occupied.add(sign_position)
            direction_entries: list[tuple[str, int]] = []
            for route in routes:
                index = route.path.index(current)
                first = world.settlements.get(route.settlement_a_id)
                second = world.settlements.get(route.settlement_b_id)
                if first is not None:
                    direction_entries.append((first.name, index))
                if second is not None:
                    direction_entries.append((
                        second.name, len(route.path) - index - 1))
            sign_seed = _stable_int(
                str(world.seed), str(x), str(y), "signpost")
            wear_level, wear_name, wear_description = (
                (
                    "light",
                    "轻度磨损",
                    "牌面边缘被风沙磨圆，刻痕里积着一层浅灰。",
                ),
                (
                    "moderate",
                    "中度磨损",
                    "木纹已经开裂，箭头一侧留有反复雨淋后的深色水痕。",
                ),
                (
                    "heavy",
                    "重度磨损",
                    "牌角残缺，旧刻字被风雨磨浅，只剩箭头轮廓仍可辨认。",
                ),
            )[sign_seed % 3]
            repair_type, repair_name, repair_description = (
                (
                    "iron_strap",
                    "铁箍加固",
                    "修补者用一圈锈铁箍重新固定了松动的木牌。",
                ),
                (
                    "replacement_board",
                    "补木修复",
                    "一块颜色较浅的新木片被钉在断裂处，钉帽还很清楚。",
                ),
                (
                    "rope_binding",
                    "绳索捆扎",
                    "立柱与横牌的接缝缠着数圈油绳，显然曾被匆忙修补。",
                ),
                (
                    "fresh_paint",
                    "重描箭头",
                    "有人用较新的赭色颜料重描了褪色箭头，笔触并不整齐。",
                ),
            )[(sign_seed // 7) % 4]
            shown_entries = [
                (name, str(distance))
                for name, distance in dict.fromkeys(direction_entries)
            ]
            repair_error_type = "none"
            repair_error_name = "修补准确"
            repair_error_description = ""
            error_roll = (sign_seed // 31) % 10
            if shown_entries and error_roll == 0:
                repair_error_type = "misspelling"
                repair_error_name = "疑似错字"
                target = (sign_seed // 191) % len(shown_entries)
                name, distance = shown_entries[target]
                shown_entries[target] = (
                    _misspell_name(name, sign_seed // 997), distance)
                repair_error_description = (
                    "补写的地名有一个字与底下的旧刻痕对不上，像是抄写时出了错。")
            elif shown_entries and error_roll == 1:
                repair_error_type = "distance_error"
                repair_error_name = "里程重写"
                target = (sign_seed // 191) % len(shown_entries)
                name, distance = shown_entries[target]
                distance_offsets = (-2, -1, 1, 2)
                offset = distance_offsets[(sign_seed // 997) % 4]
                numeric_distance = int(distance)
                shown_distance = max(1, numeric_distance + offset)
                if shown_distance == numeric_distance:
                    shown_distance = numeric_distance + 1
                shown_entries[target] = (name, str(shown_distance))
                repair_error_description = (
                    "新漆的里程数字压在旧刻痕上，两层数字并不一致。")
            elif shown_entries and error_roll == 2:
                repair_error_type = "missing_character"
                repair_error_name = "字符脱落"
                target = (sign_seed // 191) % len(shown_entries)
                name, distance = shown_entries[target]
                if (sign_seed // 503) % 3 == 0:
                    shown_entries[target] = (
                        name, _drop_text_character(distance, sign_seed // 997))
                    repair_error_description = (
                        "补写的里程有一处木屑连同数字一起脱落，残缺处没有保留原字。")
                else:
                    shown_entries[target] = (
                        _drop_text_character(name, sign_seed // 997), distance)
                    repair_error_description = (
                        "补写的地名有一处木屑连同字符一起脱落，残缺处已经看不到原字。")
            elif shown_entries and error_roll == 3:
                repair_error_type = "illegible_text"
                repair_error_name = "地名字迹模糊"
                target = (sign_seed // 191) % len(shown_entries)
                name, distance = shown_entries[target]
                shown_entries[target] = (
                    _obscure_text_character(name, sign_seed // 997), distance)
                repair_error_description = (
                    "补写的地名有一处被水渍晕开，只能看出不完整的笔画。")
            elif shown_entries and error_roll == 4:
                repair_error_type = "illegible_distance"
                repair_error_name = "距离无法辨认"
                target = (sign_seed // 191) % len(shown_entries)
                name, distance = shown_entries[target]
                shown_entries[target] = (
                    name,
                    _obscure_text_character(distance, sign_seed // 997),
                )
                repair_error_description = (
                    "里程数字有一位被泥污覆盖，那个字符已经无法辨认。")
            directions = [
                f"{name}约{distance}格"
                for name, distance in shown_entries
            ]
            entities.append(_wilderness_entity(
                entity_id=f"signpost_{x}_{y}",
                kind="landmark",
                subtype="signpost",
                position=sign_position,
                name="道路指示牌",
                role="route_marker",
                role_name="路标",
                zone="贸易道路",
                description=(
                    f"一根经风雨磨损的木制路标。{wear_description}"
                    f"修补痕迹显示有人做过{repair_name}：{repair_description}"
                    f"{repair_error_description}"
                    + "；".join(directions) + "。"),
                dialogue="；".join(directions),
                extra={
                    "wear_level": wear_level,
                    "wear_name": wear_name,
                    "repair_type": repair_type,
                    "repair_name": repair_name,
                    "repair_error_type": repair_error_type,
                    "repair_error_name": repair_error_name,
                },
            ))

        biome = str(world.geography.biomes[y, x])
        nearby_settlements = sorted(
            (settlement for settlement in world.settlements.values()
             if settlement.alive),
            key=lambda settlement: (
                abs(int(settlement.grid_x) - x)
                + abs(int(settlement.grid_y) - y),
                settlement.id,
            ),
        )
        nearest = nearby_settlements[0] if nearby_settlements else None
        religion = (
            primary_religion(nearest, world.religions)
            if nearest is not None else None)
        shrine_seed = _stable_int(
            str(world.seed), str(x), str(y), "sacred-shrine")
        distance = (
            abs(int(nearest.grid_x) - x) + abs(int(nearest.grid_y) - y)
            if nearest is not None else 999)
        landscape_match = religion is not None and (
            (religion.sacred_landscape == "river"
             and biome in {"river", "river_valley"})
            or (religion.sacred_landscape == "mountain"
                and biome in {"mountain", "highland"})
            or religion.sacred_landscape == biome
            or (religion.sacred_landscape == "spring"
                and biome in {"desert", "scrubland"})
            or (religion.sacred_landscape == "open_sky"
                and biome in {"plains", "grassland"})
        )
        should_shrine = bool(
            religion is not None and distance <= 10
            and (shrine_seed % 17 == 0
                 or (landscape_match and shrine_seed % 7 == 0)
                 or (routes and shrine_seed % 13 == 0)))
        if should_shrine:
            anchor = (
                road_candidates[min(2, len(road_candidates) - 1)]
                if road_candidates else (width // 2, height // 2))
            position = self._open_near(
                tiles, width, height, anchor, occupied,
                minimum_distance=2 if routes else 4)
            occupied.add(position)
            shrine_names = {
                "river": "水边小祠", "mountain": "山口祭石",
                "forest": "古树祭台", "spring": "旱地泉祠",
                "stone": "荒原石龛", "open_sky": "露天祈愿台",
            }
            entities.append(_wilderness_entity(
                entity_id=f"sacred_shrine_{x}_{y}",
                kind="landmark",
                subtype="sacred_shrine",
                position=position,
                name=shrine_names.get(
                    religion.sacred_landscape, "路边小祠"),
                role="sacred_site",
                role_name="荒野圣所",
                zone="道路旁" if routes else LANDSCAPE_NAMES.get(biome, "荒野"),
                description=(
                    f"几块经过摆放的石头围着刻有{religion.sacred_symbol}的"
                    f"低矮石台。残留的{religion.offering}与"
                    f"{religion.name}所记的仪次相符；石台边缘提示列席者"
                    f"{religion.congregation_response}，但风化程度显示这里并非一次建成。"),
                extra={
                    "material": "stone",
                    "blocks_movement": False,
                    "religion_name": religion.name,
                },
            ))

        trace_seed = _stable_int(str(world.seed), str(x), str(y), "traces")
        trace_specs = ROADSIDE_TRACES if routes else REMOTE_TRACES
        trace_count = 2 + trace_seed % 2 if routes else 1 + trace_seed % 2
        for trace_index in range(trace_count):
            subtype, name, description = trace_specs[
                (trace_seed // (trace_index + 1) + trace_index) % len(trace_specs)]
            position = self._seeded_open(
                tiles, width, height, roads, occupied,
                trace_seed + trace_index * 101)
            occupied.add(position)
            entities.append(_wilderness_entity(
                entity_id=f"trace_{x}_{y}_{trace_index}",
                kind="trace",
                subtype=subtype,
                position=position,
                name=name,
                role="activity_trace",
                role_name="活动痕迹",
                zone="道路附近" if routes else "荒野",
                description=description,
                extra={"blocks_movement": False},
            ))

        wildlife_specs = WILDLIFE_BY_BIOME.get(
            biome, WILDLIFE_BY_BIOME["plains"])
        wildlife_seed = _stable_int(
            str(world.seed), str(x), str(y), "wildlife")
        wildlife_count = 1 + wildlife_seed % 2
        for wildlife_index in range(wildlife_count):
            subtype, name = wildlife_specs[
                (wildlife_seed + wildlife_index) % len(wildlife_specs)]
            position = self._seeded_open(
                tiles, width, height, roads, occupied,
                wildlife_seed + wildlife_index * 211)
            occupied.add(position)
            entities.append(_wilderness_entity(
                entity_id=f"wildlife_{x}_{y}_{wildlife_index}",
                kind="wildlife",
                subtype=subtype,
                position=position,
                name=name,
                role="animal",
                role_name="野生动物",
                zone=LANDSCAPE_NAMES.get(biome, "荒野"),
                description=_wildlife_description(subtype, name),
                extra={
                    "blocks_movement": False,
                    "state": "active",
                },
            ))
        return entities

    def _wilderness_decorations(
            self, seed: int, x: int, y: int, biome: str,
            tiles: list[int], roads: set[tuple[int, int]],
            entities: list[dict], width: int, height: int) -> list[dict]:
        palette = DECORATION_PALETTES.get(
            biome, DECORATION_PALETTES["plains"])
        occupied = {(item["x"], item["y"]) for item in entities}
        decoration_seed = _stable_int(
            str(seed), str(x), str(y), "decorations")
        target_count = 45 + decoration_seed % 31
        candidates = [
            (px, py)
            for py in range(1, height - 1)
            for px in range(1, width - 1)
            if ((px, py) not in roads
                and (px, py) not in occupied
                and tiles[py * width + px] not in BLOCKING_TILES
                and tiles[py * width + px] not in {TILE_ROAD, TILE_BRIDGE})
        ]
        candidates.sort(key=lambda item: _stable_int(
            str(decoration_seed), str(item[0]), str(item[1])))
        result = []
        for index, (px, py) in enumerate(candidates[:target_count]):
            variant_seed = _stable_int(
                str(decoration_seed), str(px), str(py), "variant")
            subtype = palette[variant_seed % len(palette)]
            result.append({
                "id": f"decoration_{x}_{y}_{index}",
                "kind": "natural",
                "subtype": subtype,
                "x": px,
                "y": py,
                "variant": variant_seed % 4,
                "scale": 0.75 + (variant_seed % 51) / 100.0,
            })
        return result

    @staticmethod
    def _open_near(tiles: list[int], width: int, height: int,
                   anchor: tuple[int, int], occupied: set[tuple[int, int]],
                   minimum_distance: int = 1) -> tuple[int, int]:
        blocking = BLOCKING_TILES
        candidates = []
        for radius in range(minimum_distance, 12):
            for py in range(max(1, anchor[1] - radius),
                            min(height - 1, anchor[1] + radius + 1)):
                for px in range(max(1, anchor[0] - radius),
                                min(width - 1, anchor[0] + radius + 1)):
                    if abs(px - anchor[0]) + abs(py - anchor[1]) != radius:
                        continue
                    if ((px, py) not in occupied
                            and tiles[py * width + px] not in blocking
                            and tiles[py * width + px] not in {
                                TILE_ROAD, TILE_BRIDGE}):
                        candidates.append((px, py))
            if candidates:
                return sorted(candidates, key=lambda item: (item[1], item[0]))[0]
        return anchor

    @staticmethod
    def _seeded_open(tiles: list[int], width: int, height: int,
                     roads: set[tuple[int, int]],
                     occupied: set[tuple[int, int]], seed: int) -> tuple[int, int]:
        reachable = WorldCellMapBuilder._reachable_walkable(
            tiles, width, height)
        candidates = [
            (px, py)
            for py in range(2, height - 2)
            for px in range(2, width - 2)
            if ((px, py) in reachable
                and (px, py) not in occupied
                and (px, py) not in roads
                and tiles[py * width + px] not in BLOCKING_TILES
                and tiles[py * width + px] not in {TILE_ROAD, TILE_BRIDGE})
        ]
        if not candidates:
            return width // 2, height // 2
        return min(candidates, key=lambda item: _stable_int(
            str(seed), str(item[0]), str(item[1])))

    @staticmethod
    def _reachable_walkable(tiles: list[int], width: int,
                            height: int) -> set[tuple[int, int]]:
        start = WorldCellMapBuilder._nearest_walkable(
            tiles, width, height, (width // 2, height // 2))
        reached = {start}
        frontier = [start]
        while frontier:
            px, py = frontier.pop()
            for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                neighbor = (px + dx, py + dy)
                nx, ny = neighbor
                if (neighbor in reached or not (0 <= nx < width and 0 <= ny < height)):
                    continue
                if tiles[ny * width + nx] in BLOCKING_TILES:
                    continue
                reached.add(neighbor)
                frontier.append(neighbor)
        return reached

    def _paint_land(self, tiles: list[int], seed: int, cell_x: int,
                    cell_y: int, biome: str, width: int, height: int) -> None:
        for local_y in range(height):
            for local_x in range(width):
                gx = cell_x * (width - 1) + local_x
                gy = cell_y * (height - 1) + local_y
                noise = _stable_int(str(seed), str(gx), str(gy)) % 1000 / 1000.0
                index = local_y * width + local_x
                if biome == "forest" and noise > 0.62:
                    tiles[index] = TILE_FOREST
                elif biome == "mountain" and noise > 0.18:
                    tiles[index] = TILE_ROCK
                elif biome == "highland" and noise > 0.78:
                    tiles[index] = TILE_ROCK
                elif biome == "river_valley" and noise > 0.88:
                    tiles[index] = TILE_MARSH
                elif biome == "scrubland" and noise > 0.86:
                    tiles[index] = TILE_FOREST

    def _paint_boundary_transitions(self, tiles, geography, x, y,
                                    width, height) -> None:
        for nx, ny, edge in (
                (x, y - 1, "north"), (x, y + 1, "south"),
                (x - 1, y, "west"), (x + 1, y, "east")):
            if not (0 <= nx < geography.width and 0 <= ny < geography.height):
                continue
            neighbor = str(geography.biomes[ny, nx])
            if neighbor not in {"ocean", "lake", "mountain"}:
                continue
            tile = TILE_WATER if neighbor in {"ocean", "lake"} else TILE_ROCK
            if edge == "north":
                positions = ((px, 0) for px in range(width))
            elif edge == "south":
                positions = ((px, height - 1) for px in range(width))
            elif edge == "west":
                positions = ((0, py) for py in range(height))
            else:
                positions = ((width - 1, py) for py in range(height))
            for px, py in positions:
                tiles[py * width + px] = tile

    def _paint_river(self, tiles, geography, x, y, width, height) -> None:
        if str(geography.biomes[y, x]) != "river":
            return
        center = (width // 2, height // 2)
        portals = []
        for dx, dy in geography.river_connections(x, y):
            nx, ny = x + dx, y + dy
            offset = _edge_fraction("river", (x, y), (nx, ny))
            if dx == 0 and dy < 0:
                portals.append((round(offset * (width - 1)), 0))
            elif dx == 0 and dy > 0:
                portals.append((round(offset * (width - 1)), height - 1))
            elif dx < 0 and dy == 0:
                portals.append((0, round(offset * (height - 1))))
            elif dx > 0 and dy == 0:
                portals.append((width - 1, round(offset * (height - 1))))
            elif dx < 0 and dy < 0:
                portals.append((0, 0))
            elif dx > 0 and dy < 0:
                portals.append((width - 1, 0))
            elif dx < 0 and dy > 0:
                portals.append((0, height - 1))
            else:
                portals.append((width - 1, height - 1))
        if not portals:
            portals = [(width // 2, 0), (width // 2, height - 1)]
        for portal in dict.fromkeys(portals):
            paint_watercourse(
                tiles, width, height, (portal, center), radius=1)

    @staticmethod
    def _nearest_walkable(tiles, width, height, start):
        blocking = BLOCKING_TILES
        for radius in range(max(width, height)):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    px, py = start[0] + dx, start[1] + dy
                    if (0 <= px < width and 0 <= py < height
                            and tiles[py * width + px] not in blocking):
                        return px, py
        return start


class LocalMapRepository:
    """Session-owned lazy cache; world facts decide when a map is stale."""

    def __init__(self, world):
        self.world = world
        self.maps: dict[str, dict] = {}

    def get(self, x: int, y: int) -> dict:
        key = cell_key(x, y)
        current_signature = route_signature(self.world, x, y)
        current_site_signature = site_signature(
            self.world.get_historical_sites_at(x, y))
        cached = self.maps.get(key)
        if (cached is not None
                and cached.get("route_signature", "") == current_signature
                and cached.get("historical_site_signature", "")
                == current_site_signature):
            return cached
        settlement = self.world.get_settlement_at(x, y)
        if settlement is None:
            result = WorldCellMapBuilder().build(self.world, x, y)
        else:
            from game.local_map import LocalMapBuilder
            result = LocalMapBuilder().build(self.world, settlement)
            result["cell"] = {"x": x, "y": y}
            result["route_signature"] = current_signature
            result["historical_site_signature"] = current_site_signature
        self.maps[key] = result
        return result


def decorate_travel_groups(local_map: dict, world) -> None:
    """Project persistent camps and road parties over static terrain."""
    local_map["entities"] = [
        item for item in local_map["entities"] if not item.get("dynamic")]
    _decorate_wilderness_camps(local_map, world)
    cell = local_map.get("cell", {})
    x, y = int(cell.get("x", -1)), int(cell.get("y", -1))
    groups = world.get_travel_groups_at(x, y)
    if not groups:
        return
    width, height = local_map["width"], local_map["height"]
    road_positions = [
        (index % width, index // width)
        for index, tile in enumerate(local_map["tiles"])
        if tile in {TILE_ROAD, TILE_BRIDGE}
    ]
    road_positions.sort(key=lambda item: (
        abs(item[0] - width // 2) + abs(item[1] - height // 2),
        item[1], item[0],
    ))
    occupied = {(item["x"], item["y"]) for item in local_map["entities"]}
    for index, group in enumerate(groups):
        if (group.group_type == "traveler"
                and local_map.get("site_type") != "wilderness"):
            continue
        route = world.trade_routes[group.route_id]
        destination = world.settlements.get(group.destination_settlement_id)
        travel_path = []
        if local_map.get("site_type") == "wilderness" and road_positions:
            current = (x, y)
            route_index = route.path.index(current)
            local_direction = group.direction
            forward_index = route_index + local_direction
            if not 0 <= forward_index < len(route.path):
                local_direction *= -1
                forward_index = route_index + local_direction
            backward_index = route_index - local_direction
            hub_data = local_map.get("profile", {}).get("hub", {})
            hub = (
                int(hub_data.get("x", width // 2)),
                int(hub_data.get("y", height // 2)),
            )
            start_hint = (
                edge_portal(
                    route.id, current, route.path[backward_index],
                    width, height)
                if 0 <= backward_index < len(route.path) else hub
            )
            end_hint = (
                edge_portal(
                    route.id, current, route.path[forward_index],
                    width, height)
                if 0 <= forward_index < len(route.path) else hub
            )
            travel_path = _road_path_between(
                set(road_positions), start_hint, end_hint)
        candidates = road_positions or [
            (width // 2 + offset, height // 2)
            for offset in range(-4, 5)]
        if travel_path:
            path_index = min(
                len(travel_path) - 1,
                int(group.progress_minutes / 180 * (len(travel_path) - 1)),
            )
            position = travel_path[path_index]
        else:
            position = next(
                (item for item in candidates[index:] + candidates[:index]
                 if item not in occupied),
                candidates[index % len(candidates)],
            )
        occupied.add(position)
        common = {
            "travel_group_id": group.id,
            "route_id": route.id,
            "destination_name": destination.name if destination else "",
            "travel_path": [[px, py] for px, py in travel_path],
            "travel_clock_mode": "world_progress",
            "travel_progress": group.progress_minutes,
            "travel_duration": 180,
        }
        if group.group_type == "traveler":
            traveler_data = {
                "traveler": ("赶路的旅人", "旅人"),
                "courier": ("沿路送信的人", "信使"),
                "peddler": ("挑担行商", "行商"),
                "pilgrim": ("徒步朝圣者", "朝圣者"),
            }
            role = group.traveler_role or "traveler"
            name, role_name = traveler_data.get(
                role, traveler_data["traveler"])
            religion = (
                primary_religion(destination, world.religions)
                if destination is not None else None)
            traffic = sum(
                segment.traffic_volume
                for segment in world.get_road_segments_at(x, y)
                if route.id in segment.route_ids)
            local_map["entities"].append(_wilderness_entity(
                entity_id=group.id,
                kind="traveler",
                subtype=role,
                position=position,
                name=name,
                role=role,
                role_name=role_name,
                zone="贸易道路",
                description=(
                    f"一名正沿商路前往{destination.name if destination else '下一处聚落'}"
                    f"的{role_name}，随身物品已经按长途赶路重新捆扎。"),
                dialogue=_road_traveler_dialogue(
                    role, destination, religion,
                    group.dialogue_variant % 3, traffic),
                dynamic=True,
                extra={
                    **common,
                    "material": "cloth",
                    "religion_id": religion.id if religion is not None else "",
                    "religion_name": religion.name if religion is not None else "",
                    "travel_status": group.status,
                },
            ))
        else:
            cargo_text = "、".join(group.cargo) or "封装货物"
            local_map["entities"].append(_wilderness_entity(
                entity_id=group.id,
                kind="caravan",
                subtype="trade_caravan",
                position=position,
                name="行进中的商队",
                role="merchant",
                role_name="贸易商队",
                zone="贸易道路",
                description=(
                    f"一支由驮畜、货车和{group.guard_count}名护卫组成的商队，"
                    f"正在运送{cargo_text}。"),
                dialogue=(
                    f"领队说他们正前往{destination.name if destination else '下一处聚落'}，"
                    "也愿意告诉你前方道路和天气的情况。"),
                dynamic=True,
                extra={
                    **common,
                    "cargo": list(group.cargo),
                    "guard_count": group.guard_count,
                },
            ))


def _decorate_wilderness_camps(local_map: dict, world) -> None:
    if local_map.get("site_type") != "wilderness":
        return
    cell = local_map.get("cell", {})
    x, y = int(cell.get("x", -1)), int(cell.get("y", -1))
    camps = world.get_camps_at(x, y)
    if not camps:
        return
    width, height = local_map["width"], local_map["height"]
    tiles = local_map["tiles"]
    roads = {
        (index % width, index // width)
        for index, tile in enumerate(tiles)
        if tile in {TILE_ROAD, TILE_BRIDGE}
    }
    occupied = {
        (item["x"], item["y"])
        for item in local_map["entities"]
        if item.get("blocks_movement", True)
    }
    for camp in camps:
        specs = _camp_component_specs(camp.state)
        center = _camp_center(
            tiles, width, height, roads, occupied,
            tuple((dx, dy) for _, dx, dy, _ in specs), camp.layout_seed)
        if center is None:
            continue
        zone = {
            "occupied": "正在使用的商旅营地",
            "embers": "刚撤离的宿营地",
            "abandoned": "废弃宿营地",
            "weathered": "风化营地遗迹",
        }.get(camp.state, "荒野营地")
        for component, dx, dy, blocks in specs:
            position = center[0] + dx, center[1] + dy
            if blocks:
                occupied.add(position)
            name, role_name, material, description = _camp_component_text(
                component, camp.state)
            local_map["entities"].append(_wilderness_entity(
                entity_id=f"{camp.id}:{component}",
                kind="camp",
                subtype=component,
                position=position,
                name=name,
                role="camp_component",
                role_name=role_name,
                zone=zone,
                description=description,
                dynamic=True,
                extra={
                    "state": camp.state,
                    "material": material,
                    "blocks_movement": blocks,
                    "camp_id": camp.id,
                    "camp_state": camp.state,
                    "owner_group_id": camp.owner_group_id,
                    "component_type": component,
                },
            ))


def _camp_component_specs(state: str) -> tuple[tuple[str, int, int, bool], ...]:
    if state == "occupied":
        return (
            ("camp_tent_large", -2, -1, True),
            ("camp_tent_small", 2, -1, True),
            ("campfire_burning", 0, 1, False),
            ("camp_wagon", 3, 1, True),
            ("camp_supplies", -3, 1, True),
            ("camp_tether", 2, 3, False),
            ("camp_bedroll", -1, 3, False),
        )
    if state == "embers":
        return (
            ("campfire_embers", 0, 0, False),
            ("camp_bedroll", -2, 1, False),
            ("camp_tracks", 2, 1, False),
            ("camp_supplies", -3, -1, True),
        )
    if state == "abandoned":
        return (
            ("camp_tent_collapsed", -2, -1, True),
            ("campfire_cold", 1, 0, False),
            ("camp_crate_broken", 3, 1, True),
            ("camp_tracks", -1, 2, False),
        )
    return (
        ("campfire_ring", 0, 0, False),
        ("camp_ruts", 2, 1, False),
    )


def _camp_center(tiles: list[int], width: int, height: int,
                 roads: set[tuple[int, int]],
                 occupied: set[tuple[int, int]],
                 offsets: tuple[tuple[int, int], ...],
                 seed: int) -> tuple[int, int] | None:
    candidates = []
    for y in range(4, height - 4):
        for x in range(4, width - 4):
            footprint = {(x + dx, y + dy) for dx, dy in offsets}
            if footprint & occupied or footprint & roads:
                continue
            if any(tiles[py * width + px] in BLOCKING_TILES
                   for px, py in footprint):
                continue
            road_distance = min((
                abs(x - road_x) + abs(y - road_y)
                for road_x, road_y in roads
            ), default=4)
            if roads and not 2 <= road_distance <= 8:
                continue
            rank = _stable_int(str(seed), str(x), str(y))
            candidates.append((abs(road_distance - 4), rank, x, y))
    if not candidates:
        return None
    _, _, x, y = min(candidates)
    return x, y


def _camp_component_text(component: str, state: str) -> tuple[str, str, str, str]:
    data = {
        "camp_tent_large": (
            "商队大帐", "帐篷", "cloth", "厚帆布帐篷用木杆撑起，门帘旁挂着尚未收起的行囊。"),
        "camp_tent_small": (
            "护卫小帐", "帐篷", "cloth", "较小的帐篷靠近货车，地钉和拉绳都刚刚固定。"),
        "camp_tent_collapsed": (
            "塌陷帐篷", "废弃帐篷", "cloth", "破损篷布伏在折断的支杆上，边缘已经沾满泥土。"),
        "campfire_burning": (
            "燃烧的火塘", "火塘", "wood", "石圈中央燃着篝火，锅架和新添的木柴说明营地仍有人使用。"),
        "campfire_embers": (
            "尚热的余烬", "余烬", "ash", "火焰已经熄灭，灰层下仍透出暗红余光。"),
        "campfire_cold": (
            "冷火塘", "火塘遗迹", "ash", "雨水浸过发黑的木炭，石圈里已经感觉不到热度。"),
        "campfire_ring": (
            "风化火塘石圈", "营地遗迹", "stone", "半埋进土里的石圈和少量炭屑标记着旧宿营地的位置。"),
        "camp_wagon": (
            "停放的货车", "货车", "wood", "卸下部分货物的篷车停在帐篷旁，车轮已经用木楔固定。"),
        "camp_supplies": (
            "宿营物资", "物资堆", "wood", "木箱、饮水桶和捆扎好的草料整齐堆在防雨布下。"),
        "camp_crate_broken": (
            "破裂木箱", "遗留物资", "wood", "空木箱的一侧已经裂开，只剩断绳和潮湿填料。"),
        "camp_tether": (
            "拴畜绳桩", "拴马处", "wood", "数根短桩之间系着长绳，周围泥地布满牲畜蹄印。"),
        "camp_bedroll": (
            "铺盖与草垫", "铺盖", "cloth", "卷起一半的铺盖压在干草垫上，旁边留着水囊。"),
        "camp_tracks": (
            "密集脚印", "活动痕迹", "earth", "交叠的脚印和蹄印从营地延伸到道路，边缘仍很清楚。"),
        "camp_ruts": (
            "浅淡车辙", "风化痕迹", "earth", "两道几乎被野草覆盖的浅沟，是货车长期碾压留下的痕迹。"),
    }
    return data.get(component, (
        "营地遗物", "营地组成", "wood", f"这件遗物属于一处{state}状态的荒野营地。"))


def _road_path_between(roads: set[tuple[int, int]],
                       start: tuple[int, int],
                       end: tuple[int, int]) -> list[tuple[int, int]]:
    if not roads:
        return []
    start = min(roads, key=lambda item: (
        abs(item[0] - start[0]) + abs(item[1] - start[1]), item[1], item[0]))
    end = min(roads, key=lambda item: (
        abs(item[0] - end[0]) + abs(item[1] - end[1]), item[1], item[0]))
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        current = queue.popleft()
        if current == end:
            break
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            neighbor = (current[0] + dx, current[1] + dy)
            if neighbor in previous or neighbor not in roads:
                continue
            previous[neighbor] = current
            queue.append(neighbor)
    if end not in previous:
        return []
    path = [end]
    while previous[path[-1]] is not None:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def _road_traveler_dialogue(role: str, destination, religion,
                            variant: int, traffic: float) -> str:
    destination_name = destination.name if destination is not None else "前方聚落"
    if role == "pilgrim":
        if religion is None:
            choices = (
                f"“我准备步行到{destination_name}，在那里完成这一程的礼拜。”",
                "“路上的每一步都算在旅程里，抵达之前不能改乘车马。”",
                "“我带的供物不贵重，重要的是亲手把它送到仪式地点。”",
            )
        else:
            choices = (
                f"“我要去{destination_name}依循{religion.name}的旧仪，"
                f"献上{religion.offering}。”",
                f"“我们敬重{religion.sacred_focus}；到了{destination_name}，"
                f"我会在{religion.sacred_symbol}前完成誓愿。”",
                f"“我赶在{religion.calendar_anchor}前抵达{destination_name}，"
                f"那里的{religion.officiant}会主持仪式。”",
            )
        return choices[variant]
    if role == "courier":
        return (
            f"“这封信要在集市散场前送到{destination_name}，我不能久留。”",
            f"“我从路牌核过方向，但抵达{destination_name}前还会再问一次路。”",
            "“前一段路还能通行；若后面天气转坏，我会把送达时刻记在封套上。”",
        )[variant]
    if role == "peddler":
        return (
            f"“我去{destination_name}赶下一场集市，担子轻了才会返程。”",
            f"“这条路近来{'商旅不少' if traffic >= 60 else '行人不多'}，"
            "沿途补给得算得更仔细。”",
            f"“到了{destination_name}我先问粮价，再决定把余货换成什么。”",
        )[variant]
    return (
        f"“我准备沿这条路走到{destination_name}，天黑前能走多远算多远。”",
        "“刚才经过的路面还算完整，不过旧桥附近最好放慢脚步。”",
        f"“路上有人说{destination_name}仍有落脚处，我打算亲自去确认。”",
    )[variant]


def _wilderness_entity(*, entity_id: str, kind: str, subtype: str,
                       position: tuple[int, int], name: str, role: str,
                       role_name: str, zone: str, description: str,
                       dialogue: str = "", dynamic: bool = False,
                       extra: dict | None = None) -> dict:
    result = {
        "id": entity_id,
        "kind": kind,
        "x": position[0],
        "y": position[1],
        "name": name,
        "subtype": subtype,
        "role": role,
        "role_name": role_name,
        "state": "active" if dialogue else "weathered",
        "material": "wood",
        "zone": zone,
        "description_cn": description,
        "dialogue_cn": dialogue,
        "blocks_movement": True,
        "dynamic": dynamic,
    }
    result.update(extra or {})
    return result


def _edge_fraction(feature_id: str, first: tuple[int, int],
                   second: tuple[int, int]) -> float:
    low, high = sorted((first, second))
    value = _stable_int(feature_id, str(low), str(high)) % 7001 + 1500
    return value / 10000.0


def _carve(tiles, width, height, start, end, roads, seed,
           status="active"):
    x, y = start
    horizontal_first = seed % 2 == 0
    while (x, y) != end:
        _paint_road(tiles, width, height, x, y, roads, status, seed)
        if x != end[0] and y != end[1]:
            move_x = horizontal_first if (abs(x - end[0]) + abs(y - end[1])) % 5 else not horizontal_first
        else:
            move_x = x != end[0]
        if move_x:
            x += 1 if end[0] > x else -1
        else:
            y += 1 if end[1] > y else -1
    _paint_road(tiles, width, height, x, y, roads, status, seed)


def _paint_road(tiles, width, height, x, y, roads,
                status="active", seed=0):
    for px in (x, min(width - 1, x + 1)):
        if (status == "overgrown"
                and _stable_int(str(seed), str(px), str(y)) % 3 != 0):
            continue
        index = y * width + px
        if status == "overgrown":
            tiles[index] = TILE_RUBBLE
        else:
            tiles[index] = (
                TILE_BRIDGE
                if tiles[index] in {TILE_WATER, TILE_BRIDGE}
                else TILE_ROAD
            )
        roads.add((px, y))


def _carve_water(tiles, width, height, start, end):
    paint_watercourse(tiles, width, height, (start, end), radius=1)


def _stable_int(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(
        "|".join(parts).encode("utf-8")).digest()[:8], "big")


def _misspell_name(name: str, seed: int) -> str:
    if len(name) < 2:
        return f"{name}驿"
    characters = list(name)
    index = seed % (len(characters) - 1)
    if characters[index] == characters[index + 1]:
        characters[index] = "驿"
    else:
        characters[index], characters[index + 1] = (
            characters[index + 1], characters[index])
    return "".join(characters)


def _drop_text_character(text: str, seed: int) -> str:
    if len(text) < 2:
        return ""
    index = seed % len(text)
    return text[:index] + text[index + 1:]


def _obscure_text_character(text: str, seed: int) -> str:
    if not text:
        return "？"
    index = seed % len(text)
    return text[:index] + "？" + text[index + 1:]


def _wildlife_description(subtype: str, name: str) -> str:
    behavior = {
        "deer": "它不时抬头观察四周，随后低头啃食草叶。",
        "hare": "它贴着低矮植被停停走走，听到动静便立刻竖起耳朵。",
        "heron": "它沿湿地缓慢踱步，偶尔把长喙探入浅水。",
        "waterfowl": "它在水边整理羽毛，受惊时会迅速退向芦苇深处。",
        "mountain_goat": "它稳稳站在碎石地上，沿坡面寻找稀疏草叶。",
        "ptarmigan": "它在石块和低草之间啄食，羽色与周围地面十分接近。",
        "fox": "它压低身体嗅闻地面，对远处的响动保持警觉。",
        "lizard": "它伏在温暖地面上，阴影靠近时便短促地窜向掩体。",
    }.get(subtype, "它在植被和石块之间谨慎活动，始终留意周围动静。")
    return f"一只生活在这片荒野中的{name}。{behavior}"
