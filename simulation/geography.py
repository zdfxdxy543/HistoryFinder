"""Deterministic terrain, climate, hydrology, biomes, and settlement sites."""

import heapq
import math
import random
import numpy as np

try:
    from noise import snoise2
except ImportError:
    # 如果没有 noise 库，用简易 fallback
    snoise2 = None

from config import (
    GRID_WIDTH, GRID_HEIGHT,
    NOISE_SCALE, NOISE_OCTAVES, NOISE_PERSISTENCE, NOISE_LACUNARITY,
    SEA_LEVEL, RIVER_FLOW_PERCENTILE, MIN_SETTLEMENT_DISTANCE,
)
from simulation.geographic_features import (
    GeographicFeature,
    generate_geographic_features,
)


def _fbm_noise(x: float, y: float, seed: int, octaves: int = NOISE_OCTAVES) -> float:
    """Fractal Brownian Motion 叠加多层噪声。"""
    if snoise2 is None:
        # 纯 numpy 伪随机 fallback
        return _simple_noise(x, y, seed)

    value = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_value = 0.0

    for i in range(octaves):
        nx = x * frequency * NOISE_SCALE
        ny = y * frequency * NOISE_SCALE
        value += amplitude * snoise2(nx + seed * 0.1, ny + seed * 0.1)
        max_value += amplitude
        amplitude *= NOISE_PERSISTENCE
        frequency *= NOISE_LACUNARITY

    return value / max_value


def _simple_noise(x: float, y: float, seed: int) -> float:
    """无 noise 库时的降级方案——用 numpy 模拟简单地形。"""
    np.random.seed(int(abs(x * 1000 + y * 100 + seed * 13)) % (2**31 - 1))
    return np.random.uniform(-1, 1)


def generate_heightmap(width: int, height: int, seed: int) -> np.ndarray:
    """Generate continent-scale landforms with detailed ridges and ocean edges."""
    hmap = np.zeros((height, width), dtype=np.float32)
    for y in range(height):
        for x in range(width):
            broad = (_fbm_noise(
                x * 0.38, y * 0.38, seed + 17, 3) + 1.0) / 2.0
            detail = (_fbm_noise(
                x, y, seed, NOISE_OCTAVES) + 1.0) / 2.0
            ridge_noise = _fbm_noise(
                x * 0.62, y * 0.62, seed + 71, 3)
            ridges = (1.0 - abs(ridge_noise)) ** 6

            # Force coastlines near the map boundary without imposing a circle.
            nx = x / max(width - 1, 1) * 2.0 - 1.0
            ny = y / max(height - 1, 1) * 2.0 - 1.0
            edge_distance = max(abs(nx), abs(ny))
            edge_falloff = max(
                0.0, (edge_distance - 0.58) / 0.42) ** 1.6

            raw = (0.52 * broad + 0.32 * detail + 0.12 * ridges
                   - 0.55 * edge_falloff)
            hmap[y, x] = np.clip((raw + 0.08) / 0.82, 0.0, 1.0)
    return hmap


def generate_temperature(hmap: np.ndarray, seed: int) -> np.ndarray:
    """
    温度分布：纬度主导 + 海拔修正。
    北冷南暖（简化：上方=北=冷）。
    """
    h, w = hmap.shape
    temp = np.zeros_like(hmap)
    for y in range(h):
        # 纬度因子：0（顶部/北）= 冷，h-1（底部/南）= 暖
        lat_factor = y / (h - 1)  # 0~1
        base_temp = 3.0 + lat_factor * 27.0  # 3°C ~ 30°C
        for x in range(w):
            elevation = hmap[y, x]
            land_height = max(0.0, elevation - SEA_LEVEL) / (1.0 - SEA_LEVEL)
            elevation_m = land_height * 4200.0
            regional = _fbm_noise(
                x * 0.55, y * 0.55, seed + 101, 2) * 2.2
            value = base_temp - (elevation_m / 100.0) * 0.6 + regional
            if elevation <= SEA_LEVEL:
                # Water moderates extremes but keeps the latitude gradient.
                value = 0.75 * base_temp + 0.25 * 14.0 + regional * 0.4
            temp[y, x] = value
    return temp


def generate_rainfall(hmap: np.ndarray, temp: np.ndarray, seed: int) -> np.ndarray:
    """
    降雨：纬度带 + 简化雨影效应。
    简化：西风带从左侧吹向右侧，遇到山脉在右侧减雨。
    """
    h, w = hmap.shape
    rainfall = np.zeros_like(hmap)
    for y in range(h):
        latitude = y / max(h - 1, 1)
        latitude_dryness = abs(latitude - 0.55) * 1.65
        latitude_moisture = np.clip(1.0 - latitude_dryness, 0.15, 1.0)
        subtropical_dry_belt = np.exp(-((latitude - 0.78) / 0.12) ** 2)
        atmospheric_moisture = 0.65 + latitude_moisture * 0.35
        for x in range(w):
            elevation = hmap[y, x]
            regional = (_fbm_noise(
                x * 0.72, y * 0.72, seed + 211, 2) + 1.0) / 2.0
            if elevation <= SEA_LEVEL:
                rainfall[y, x] = 125.0 + latitude_moisture * 75.0
                atmospheric_moisture = min(
                    1.25, atmospheric_moisture + 0.18)
                continue

            west_height = hmap[y, x - 1] if x > 0 else SEA_LEVEL
            upslope = max(0.0, elevation - west_height)
            convective = np.clip((temp[y, x] + 5.0) / 35.0, 0.2, 1.15)
            base_rain = ((38.0 + 140.0 * latitude_moisture)
                         * (1.0 - 0.58 * subtropical_dry_belt))
            orographic = 1.0 + min(1.2, upslope * 7.0)
            rain = (base_rain * (0.42 + atmospheric_moisture * 0.58)
                    * orographic * (0.78 + regional * 0.44)
                    * (0.78 + convective * 0.22))
            rainfall[y, x] = np.clip(rain, 12.0, 280.0)

            # Westerly air loses moisture as it climbs and slowly recovers.
            atmospheric_moisture = np.clip(
                atmospheric_moisture - rain / 4800.0 - upslope * 0.65
                + 0.028,
                0.16,
                1.25,
            )
    return rainfall


def generate_hydrology(hmap: np.ndarray, rainfall: np.ndarray,
                       seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build drainage-connected rivers and lakes with priority-flood routing."""
    del seed  # Routing is already deterministic from terrain and rainfall.
    h, w = hmap.shape
    ocean = hmap <= SEA_LEVEL
    filled = hmap.astype(np.float64).copy()
    visited = ocean.copy()
    downstream_y = np.full((h, w), -1, dtype=np.int32)
    downstream_x = np.full((h, w), -1, dtype=np.int32)
    queue: list[tuple[float, int, int]] = []

    for y, x in np.argwhere(ocean):
        heapq.heappush(queue, (float(filled[y, x]), int(y), int(x)))

    # Maps with no ocean still drain through their boundary.
    if not queue:
        for x in range(w):
            for y in (0, h - 1):
                if not visited[y, x]:
                    visited[y, x] = True
                    heapq.heappush(queue, (float(filled[y, x]), y, x))
        for y in range(h):
            for x in (0, w - 1):
                if not visited[y, x]:
                    visited[y, x] = True
                    heapq.heappush(queue, (float(filled[y, x]), y, x))

    directions = [
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1),
    ]
    epsilon = 1e-7
    while queue:
        surface, y, x = heapq.heappop(queue)
        for dy, dx in directions:
            ny, nx = y + dy, x + dx
            if not (0 <= ny < h and 0 <= nx < w) or visited[ny, nx]:
                continue
            visited[ny, nx] = True
            downstream_y[ny, nx] = y
            downstream_x[ny, nx] = x
            filled[ny, nx] = max(float(hmap[ny, nx]), surface + epsilon)
            heapq.heappush(queue, (float(filled[ny, nx]), ny, nx))

    land = ~ocean
    runoff = np.where(land, 0.35 + rainfall / 140.0, 0.0).astype(np.float64)
    accumulation = runoff.copy()
    land_cells = np.argwhere(land)
    order = sorted(
        ((float(filled[y, x]), int(y), int(x)) for y, x in land_cells),
        reverse=True,
    )
    for _, y, x in order:
        ny, nx = downstream_y[y, x], downstream_x[y, x]
        if ny >= 0:
            accumulation[ny, nx] += accumulation[y, x]

    depression_depth = filled - hmap
    lakes = land & (depression_depth > 0.07)
    drainage_values = accumulation[land & ~lakes]
    threshold = (np.percentile(drainage_values, RIVER_FLOW_PERCENTILE)
                 if drainage_values.size else float("inf"))
    threshold = max(18.0, float(threshold))
    rivers = land & ~lakes & (accumulation >= threshold)

    return (rivers.astype(np.float32), lakes.astype(np.float32),
            accumulation.astype(np.float32))


def generate_rivers(hmap: np.ndarray, rainfall: np.ndarray,
                    seed: int) -> np.ndarray:
    """Backward-compatible river-only view of the hydrology pipeline."""
    rivers, _, _ = generate_hydrology(hmap, rainfall, seed)
    return rivers


def classify_biomes(hmap: np.ndarray, temp: np.ndarray, rainfall: np.ndarray,
                    rivers: np.ndarray, lakes: np.ndarray | None = None) -> np.ndarray:
    """
    根据 (海拔, 温度, 降雨, 河流) 分类生物群系。
    返回字符串数组。
    """
    h, w = hmap.shape
    biomes = np.empty((h, w), dtype=object)
    lakes = np.zeros_like(rivers) if lakes is None else lakes

    near_river = np.zeros_like(rivers, dtype=bool)
    for y, x in np.argwhere(rivers > 0):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    near_river[ny, nx] = True

    for y in range(h):
        for x in range(w):
            e = hmap[y, x]
            t = temp[y, x]
            r = rainfall[y, x]
            is_river = rivers[y, x] == 1

            if e <= SEA_LEVEL:
                biomes[y, x] = "ocean"
            elif lakes[y, x]:
                biomes[y, x] = "lake"
            elif is_river:
                biomes[y, x] = "river"
            elif e > 0.86:
                biomes[y, x] = "mountain"
            elif e > 0.72:
                biomes[y, x] = "highland"
            elif near_river[y, x] and e < 0.62:
                biomes[y, x] = "river_valley"
            elif t < 3:
                biomes[y, x] = "tundra"
            elif t > 7 and r > 145:
                biomes[y, x] = "forest"
            elif t > 10 and r < 55:
                biomes[y, x] = "desert"
            elif t > 7 and r > 72:
                biomes[y, x] = "grassland"
            elif r < 62:
                biomes[y, x] = "scrubland"
            else:
                biomes[y, x] = "plains"

    return biomes


def settlement_suitability(hmap: np.ndarray, rainfall: np.ndarray,
                           rivers: np.ndarray, biomes: np.ndarray,
                           lakes: np.ndarray | None = None) -> np.ndarray:
    """
    计算每个格子的聚落适宜度 [0, 1]。
    水源×0.35 + 肥沃度(降雨/生物群系)×0.25 + 防御性(海拔)×0.20
    + 资源(森林/山谷)×0.15 + 中心度×0.05
    """
    h, w = hmap.shape

    lakes = np.zeros_like(rivers) if lakes is None else lakes
    water_proximity = np.zeros_like(hmap)
    for y in range(h):
        for x in range(w):
            if rivers[y, x] or lakes[y, x]:
                for dy in range(-4, 5):
                    for dx in range(-4, 5):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            dist = max(abs(dy), abs(dx))
                            water_proximity[ny, nx] = max(
                                water_proximity[ny, nx],
                                1.0 - dist / 5.0
                            )
            elif biomes[y, x] == "ocean":
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w:
                            dist = max(abs(dy), abs(dx))
                            water_proximity[ny, nx] = max(
                                water_proximity[ny, nx],
                                0.45 * (1.0 - dist / 3.0),
                            )

    fertility = np.zeros_like(hmap)
    for y in range(h):
        for x in range(w):
            b = biomes[y, x]
            r = rainfall[y, x]
            if b in ("river_valley", "grassland", "forest"):
                fertility[y, x] = 0.8 + (r / 200.0) * 0.2
            elif b in ("plains",):
                fertility[y, x] = 0.5 + (r / 200.0) * 0.2
            elif b in ("scrubland", "highland"):
                fertility[y, x] = 0.3 + (r / 200.0) * 0.1
            else:
                fertility[y, x] = 0.1

    land_height = np.clip(
        (hmap - SEA_LEVEL) / (1.0 - SEA_LEVEL), 0.0, 1.0)
    defensibility = np.clip(land_height * 1.6, 0.1, 0.9)

    resource = np.zeros_like(hmap)
    for y in range(h):
        for x in range(w):
            b = biomes[y, x]
            if b == "forest":
                resource[y, x] = 0.8
            elif b == "river_valley":
                resource[y, x] = 0.9
            elif b == "mountain":
                resource[y, x] = 0.7  # 矿产
            elif b == "highland":
                resource[y, x] = 0.6
            else:
                resource[y, x] = 0.4

    # 中心度：越靠近地图中心越好（简化贸易优势）
    center_y, center_x = h / 2, w / 2
    centrality = np.zeros_like(hmap)
    for y in range(h):
        for x in range(w):
            dist = np.sqrt((y - center_y)**2 + (x - center_x)**2)
            max_dist = np.sqrt(center_y**2 + center_x**2)
            centrality[y, x] = 1.0 - dist / max_dist

    suitability = (
        water_proximity * 0.35 +
        fertility * 0.25 +
        defensibility * 0.20 +
        resource * 0.15 +
        centrality * 0.05
    )

    blocked = np.isin(biomes, ["ocean", "lake", "river", "mountain"])
    suitability[blocked] = 0.0
    suitability[hmap > 0.78] *= 0.35

    return suitability


def pick_settlement_sites(suitability: np.ndarray, count: int, seed: int) -> list[tuple[int, int]]:
    """
    选出 top N 个适宜位置，但加上空间分散约束。
    返回 [(x, y), ...] 列表。
    """
    h, w = suitability.shape
    rng = np.random.RandomState(seed + 400)

    ranking = suitability + rng.uniform(0.0, 0.012, suitability.shape)
    ranking[suitability <= 0.0] = -1.0
    flat_indices = np.argsort(ranking.ravel())[::-1]
    sites = []
    used_positions = set()

    for idx in flat_indices:
        y, x = idx // w, idx % w
        # 检查与已选位置的最小距离
        too_close = False
        for sx, sy in used_positions:
            if abs(x - sx) + abs(y - sy) < MIN_SETTLEMENT_DISTANCE:
                too_close = True
                break
        if too_close:
            continue
        sites.append((x, y))
        used_positions.add((x, y))
        if len(sites) >= count:
            break

    if len(sites) < count:
        raise RuntimeError(
            f"only found {len(sites)} valid settlement sites for {count} settlements")

    return sites


class Geography:
    """地理数据容器。"""

    def __init__(self, seed: int):
        self.seed = seed
        self.width = GRID_WIDTH
        self.height = GRID_HEIGHT

        # 核心图层
        self.heightmap: np.ndarray = None
        self.temperature: np.ndarray = None
        self.rainfall: np.ndarray = None
        self.rivers: np.ndarray = None
        self.lakes: np.ndarray = None
        self.flow_accumulation: np.ndarray = None
        self.biomes: np.ndarray = None
        self.suitability: np.ndarray = None
        self.features: list[GeographicFeature] = []
        self._features_by_cell: dict[
            tuple[int, int], list[GeographicFeature]] = {}

    def generate(self):
        """执行完整地理生成管线。"""
        self.heightmap = generate_heightmap(self.width, self.height, self.seed)
        self.temperature = generate_temperature(self.heightmap, self.seed)
        self.rainfall = generate_rainfall(self.heightmap, self.temperature, self.seed)
        self.rivers, self.lakes, self.flow_accumulation = generate_hydrology(
            self.heightmap, self.rainfall, self.seed)
        self.biomes = classify_biomes(
            self.heightmap, self.temperature, self.rainfall,
            self.rivers, self.lakes)
        self.suitability = settlement_suitability(
            self.heightmap, self.rainfall, self.rivers,
            self.biomes, self.lakes)
        self.features = generate_geographic_features(
            self.seed, self.biomes, self.heightmap,
            self.rainfall, self.temperature)
        self._features_by_cell = {}
        for feature in self.features:
            for cell in feature.cells:
                self._features_by_cell.setdefault(cell, []).append(feature)

    def get_features_at(self, x: int, y: int) -> list[GeographicFeature]:
        return list(self._features_by_cell.get((x, y), ()))

    def nearest_features(
            self, x: int, y: int, feature_types: set[str] | None = None,
            max_distance: float | None = None, limit: int = 1,
    ) -> list[GeographicFeature]:
        candidates = [
            feature for feature in self.features
            if feature_types is None or feature.feature_type in feature_types
        ]
        ranked = []
        for feature in candidates:
            left, top, right, bottom = feature.bounds
            bounds_distance = math.hypot(
                max(left - x, 0, x - right),
                max(top - y, 0, y - bottom),
            )
            if max_distance is not None and bounds_distance > max_distance:
                continue
            distance = min(
                math.hypot(cell_x - x, cell_y - y)
                for cell_x, cell_y in feature.cells)
            if max_distance is None or distance <= max_distance:
                ranked.append((distance, -feature.importance, feature.id, feature))
        ranked.sort(key=lambda item: item[:3])
        return [item[3] for item in ranked[:max(0, limit)]]

    def get_biome_name(self, x: int, y: int) -> str:
        """返回中文生物群系名。"""
        mapping = {
            "mountain": "山脉",
            "highland": "高地",
            "ocean": "海洋",
            "lake": "湖泊",
            "river": "河流",
            "river_valley": "河谷",
            "forest": "森林",
            "desert": "沙漠",
            "grassland": "草原",
            "tundra": "冻土",
            "scrubland": "灌木地",
            "plains": "平原",
        }
        b = self.biomes[y, x]
        return mapping.get(b, str(b))
