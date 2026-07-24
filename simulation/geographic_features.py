"""Deterministic geographic feature extraction and rule-based naming."""

from __future__ import annotations

import hashlib
import math
import random
from collections import deque
from dataclasses import dataclass

import numpy as np


FEATURE_TYPE_NAMES = {
    "river": "河流",
    "lake": "湖泊",
    "mountain": "山地",
    "plains": "平原",
    "forest": "森林",
    "desert": "荒地",
    "tundra": "苔原",
}

FEATURE_SUFFIXES = {
    "river": ("河", "川", "溪", "水"),
    "lake": ("湖", "泽", "泊"),
    "mountain": ("岭", "山", "峰群", "山脉"),
    "plains": ("原", "平野", "草原", "原野"),
    "forest": ("林", "森林", "树海", "密林"),
    "desert": ("荒原", "沙地", "旷野", "荒漠"),
    "tundra": ("冻原", "寒原", "苔原", "霜野"),
}

# These are semantic morphemes, not completed place names. Their tags let the
# generator select material that agrees with the actual terrain.
COLOR_MATERIALS = {
    "neutral": (
        "苍", "青", "白", "灰", "银", "玄", "赤", "金", "翠", "黛",
        "褐", "蓝", "乌", "素", "丹", "碧",
    ),
    "cold": ("霜", "雪", "白", "银", "苍", "冰", "寒", "青"),
    "warm": ("赤", "金", "丹", "褐", "炎", "暖", "朱", "黄"),
    "wet": ("碧", "青", "雾", "雨", "澄", "镜", "潮", "蓝"),
    "dry": ("赤", "灰", "白", "砂", "尘", "燥", "赭", "褐"),
    "high": ("云", "天", "霜", "雪", "风", "鹰", "石", "苍"),
}

ECOLOGY_MATERIALS = {
    "river": (
        "苇", "芦", "柳", "鲤", "鹭", "荷", "湾", "滩", "汀", "藻",
        "蒲", "渡", "泉", "涧", "沙洲", "回湾",
    ),
    "lake": (
        "镜", "鹤", "苇", "莲", "雁", "蒲", "月", "湾", "岛", "汀",
        "静水", "芦影", "鱼", "浅湾",
    ),
    "mountain": (
        "脊", "冠", "鹰", "松", "石", "崖", "刃", "角", "峰", "隘",
        "岩", "云", "风口", "断壁", "双峰", "高脊",
    ),
    "plains": (
        "麦", "穗", "长草", "鹿", "风", "野花", "牧", "沃土", "草浪",
        "百泉", "芳草", "田", "谷穗", "远草", "平畴",
    ),
    "forest": (
        "松", "杉", "橡", "桦", "榆", "鹿", "狐", "鸦", "苔", "蕨",
        "藤", "木", "幽叶", "深枝", "青荫", "古树",
    ),
    "desert": (
        "沙", "砾", "盐", "风蚀", "旱", "蜥", "枯井", "石柱", "尘",
        "赤岩", "白沙", "干河", "荒草", "热风",
    ),
    "tundra": (
        "霜", "冰", "苔", "雪兔", "寒风", "冻土", "白草", "石楠",
        "长夜", "北光", "冷泉", "雪原", "孤石",
    ),
}

SHAPE_MATERIALS = {
    "river": (
        "长", "曲", "双", "回", "浅", "深", "急", "缓", "三湾", "九曲",
        "东流", "西折", "宽", "细", "环",
    ),
    "lake": (
        "圆", "长", "弯", "双", "深", "浅", "静", "裂", "环", "半月",
        "三岛", "狭", "广",
    ),
    "mountain": (
        "断", "长", "双", "尖", "裂", "高", "横", "环", "北向", "层叠",
        "三峰", "孤", "连", "陡",
    ),
    "plains": (
        "长", "广", "东", "西", "北", "南", "低", "开阔", "百里", "无垠",
        "缓坡", "中央",
    ),
    "forest": (
        "深", "长", "幽", "密", "东", "西", "北", "南", "环", "古",
        "高木", "低枝",
    ),
    "desert": (
        "长", "广", "东", "西", "北", "南", "无水", "裂", "空", "百里",
        "低洼", "高燥",
    ),
    "tundra": (
        "北", "长", "广", "空", "高", "低", "无树", "风切", "漫长",
        "白", "灰",
    ),
}

DISALLOWED_MATERIALS = {
    "forest": {"炎", "燥", "砂", "尘", "赭", "镜", "潮", "澄"},
    "desert": {"碧", "翠", "澄", "镜", "潮", "蓝", "雨"},
    "tundra": {"炎", "暖", "朱", "燥", "赤", "丹", "黄", "金"},
    "river": {"燥", "炎"},
    "lake": {"燥", "炎", "尘"},
}


@dataclass(frozen=True)
class GeographicFeature:
    id: str
    feature_type: str
    name: str
    cells: tuple[tuple[int, int], ...]
    anchor: tuple[int, int]
    bounds: tuple[int, int, int, int]
    size: int
    mean_elevation: float
    mean_rainfall: float
    mean_temperature: float
    importance: float
    min_zoom: float
    name_parts: tuple[str, ...]
    meaning_tags: tuple[str, ...]

    def to_dict(self, *, include_cells: bool = False) -> dict:
        result = {
            "id": self.id,
            "feature_type": self.feature_type,
            "feature_type_name": FEATURE_TYPE_NAMES[self.feature_type],
            "name": self.name,
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
            "bounds": list(self.bounds),
            "size": self.size,
            "importance": self.importance,
            "min_zoom": self.min_zoom,
            "name_parts": list(self.name_parts),
            "meaning_tags": list(self.meaning_tags),
        }
        if include_cells:
            result["cells"] = [[x, y] for x, y in self.cells]
        return result


FEATURE_SPECS = (
    ("river", {"river"}, 4, True),
    ("lake", {"lake"}, 3, True),
    ("mountain", {"mountain", "highland"}, 10, True),
    ("plains", {"plains", "grassland"}, 18, False),
    ("forest", {"forest"}, 14, False),
    ("desert", {"desert", "scrubland"}, 14, False),
    ("tundra", {"tundra"}, 14, False),
)


def generate_geographic_features(
        seed: int, biomes: np.ndarray, heightmap: np.ndarray,
        rainfall: np.ndarray, temperature: np.ndarray,
) -> list[GeographicFeature]:
    """Identify continuous terrain regions and assign stable unique names."""
    drafts = []
    for feature_type, biome_types, minimum_size, diagonal in FEATURE_SPECS:
        mask = np.isin(biomes, list(biome_types))
        for cells in _connected_components(mask, diagonal=diagonal):
            if len(cells) < minimum_size:
                continue
            drafts.append(_feature_draft(
                feature_type, cells, heightmap, rainfall, temperature))

    maximum_by_type: dict[str, int] = {}
    for draft in drafts:
        maximum_by_type[draft["feature_type"]] = max(
            maximum_by_type.get(draft["feature_type"], 0), draft["size"])
    drafts.sort(key=lambda item: (
        item["feature_type"], -item["size"], item["bounds"][1],
        item["bounds"][0]))

    used_names: set[str] = set()
    type_rank: dict[str, int] = {}
    features = []
    for draft in drafts:
        feature_type = draft["feature_type"]
        rank = type_rank.get(feature_type, 0)
        type_rank[feature_type] = rank + 1
        maximum = maximum_by_type[feature_type]
        importance = draft["size"] / max(1, maximum)
        min_zoom = 1.0 if rank < 2 or importance >= 0.35 else (
            1.75 if importance >= 0.14 else 2.75)
        feature_id = _feature_id(feature_type, draft["cells"])
        name, parts, tags = _generate_feature_name(
            seed, feature_id, draft, used_names)
        features.append(GeographicFeature(
            id=feature_id,
            feature_type=feature_type,
            name=name,
            cells=draft["cells"],
            anchor=draft["anchor"],
            bounds=draft["bounds"],
            size=draft["size"],
            mean_elevation=draft["mean_elevation"],
            mean_rainfall=draft["mean_rainfall"],
            mean_temperature=draft["mean_temperature"],
            importance=round(importance, 4),
            min_zoom=min_zoom,
            name_parts=parts,
            meaning_tags=tags,
        ))
    return sorted(features, key=lambda item: item.id)


def _connected_components(mask: np.ndarray, *, diagonal: bool
                          ) -> list[tuple[tuple[int, int], ...]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    directions = [(-1, 0), (0, -1), (1, 0), (0, 1)]
    if diagonal:
        directions += [(-1, -1), (1, -1), (-1, 1), (1, 1)]
    result = []
    for y, x in np.argwhere(mask):
        y, x = int(y), int(x)
        if visited[y, x]:
            continue
        visited[y, x] = True
        queue = deque([(x, y)])
        cells = []
        while queue:
            current_x, current_y = queue.popleft()
            cells.append((current_x, current_y))
            for dx, dy in directions:
                next_x, next_y = current_x + dx, current_y + dy
                if (not 0 <= next_x < width or not 0 <= next_y < height
                        or visited[next_y, next_x]
                        or not mask[next_y, next_x]):
                    continue
                visited[next_y, next_x] = True
                queue.append((next_x, next_y))
        result.append(tuple(sorted(cells, key=lambda item: (item[1], item[0]))))
    return result


def _feature_draft(feature_type: str, cells: tuple[tuple[int, int], ...],
                   heightmap: np.ndarray, rainfall: np.ndarray,
                   temperature: np.ndarray) -> dict:
    xs = [item[0] for item in cells]
    ys = [item[1] for item in cells]
    center_x = sum(xs) / len(xs)
    center_y = sum(ys) / len(ys)
    anchor = min(cells, key=lambda item: (
        (item[0] - center_x) ** 2 + (item[1] - center_y) ** 2,
        item[1], item[0]))
    values = [(y, x) for x, y in cells]
    return {
        "feature_type": feature_type,
        "cells": cells,
        "anchor": anchor,
        "bounds": (min(xs), min(ys), max(xs), max(ys)),
        "size": len(cells),
        "mean_elevation": float(np.mean([heightmap[y, x] for y, x in values])),
        "mean_rainfall": float(np.mean([rainfall[y, x] for y, x in values])),
        "mean_temperature": float(np.mean([temperature[y, x] for y, x in values])),
    }


def _feature_id(feature_type: str,
                cells: tuple[tuple[int, int], ...]) -> str:
    first = cells[0]
    payload = ";".join(f"{x},{y}" for x, y in cells)
    digest = hashlib.sha256(payload.encode("ascii")).hexdigest()[:8]
    return f"geo_{feature_type}_{first[0]}_{first[1]}_{digest}"


def _generate_feature_name(seed: int, feature_id: str, draft: dict,
                           used_names: set[str]
                           ) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    feature_type = draft["feature_type"]
    tags = _terrain_tags(draft)
    colors = list(COLOR_MATERIALS["neutral"])
    for tag in tags:
        colors.extend(COLOR_MATERIALS.get(tag, ()))
    disallowed = DISALLOWED_MATERIALS.get(feature_type, set())
    colors = list(dict.fromkeys(
        item for item in colors if item not in disallowed))
    ecology = list(ECOLOGY_MATERIALS[feature_type])
    shapes = list(SHAPE_MATERIALS[feature_type])
    suffixes = list(FEATURE_SUFFIXES[feature_type])
    rng = random.Random(_stable_int(str(seed), feature_id, "name"))
    candidates = []
    for _ in range(64):
        pattern = rng.randrange(5)
        if pattern == 0:
            parts = (rng.choice(colors), rng.choice(ecology), rng.choice(suffixes))
        elif pattern == 1:
            parts = (rng.choice(shapes), rng.choice(ecology), rng.choice(suffixes))
        elif pattern == 2:
            parts = (rng.choice(colors), rng.choice(shapes), rng.choice(suffixes))
        elif pattern == 3:
            parts = (rng.choice(ecology), rng.choice(suffixes))
        else:
            parts = (rng.choice(shapes), rng.choice(suffixes))
        name = "".join(parts)
        if _valid_name(name, parts) and name not in candidates:
            candidates.append(name)
    for name in candidates:
        if name.casefold() in used_names:
            continue
        used_names.add(name.casefold())
        suffix = next(
            item for item in suffixes if name.endswith(item))
        root = name[:-len(suffix)]
        return name, (root, suffix), tags
    fallback = f"{FEATURE_TYPE_NAMES[feature_type]}{len(used_names) + 1}号"
    used_names.add(fallback.casefold())
    return fallback, (fallback,), tags


def _terrain_tags(draft: dict) -> tuple[str, ...]:
    tags = []
    temperature = draft["mean_temperature"]
    rainfall = draft["mean_rainfall"]
    elevation = draft["mean_elevation"]
    left, top, right, bottom = draft["bounds"]
    if temperature <= 5:
        tags.append("cold")
    elif temperature >= 20:
        tags.append("warm")
    if rainfall >= 145:
        tags.append("wet")
    elif rainfall <= 62:
        tags.append("dry")
    if elevation >= 0.75:
        tags.append("high")
    if max(right - left, bottom - top) >= math.sqrt(draft["size"]) * 2.2:
        tags.append("long")
    return tuple(tags or ("neutral",))


def _valid_name(name: str, parts: tuple[str, ...]) -> bool:
    if not 2 <= len(name) <= 7:
        return False
    if any(first == second for first, second in zip(parts, parts[1:])):
        return False
    if any(first[-1] == second[0]
           for first, second in zip(parts, parts[1:])):
        return False
    return not any(name.count(character) >= 3 for character in set(name))


def _stable_int(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(
        "|".join(parts).encode("utf-8")).digest()[:8], "big")
