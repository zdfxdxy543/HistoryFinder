"""
HistoryFinder — 全局配置
"""

import os

# ---- 路径 ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WORLDS_DIR = os.path.join(DATA_DIR, "worlds")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

# ---- 模拟参数（Phase 1） ----
GRID_WIDTH = 200
GRID_HEIGHT = 200
SIM_YEARS = 100
RANDOM_SEED = 42

# ---- 聚落参数 ----
INITIAL_SETTLEMENT_COUNT = 8
BASE_POPULATION = 100
MAX_POPULATION_PER_CELL = 5000

# ---- 地理参数 ----
# 噪声缩放：越小 → 大陆越大
NOISE_SCALE = 0.03
NOISE_OCTAVES = 4
NOISE_PERSISTENCE = 0.5
NOISE_LACUNARITY = 2.0
SEA_LEVEL = 0.32
RIVER_FLOW_PERCENTILE = 96.5
MIN_SETTLEMENT_DISTANCE = 18

# ---- 证据参数 ----
MATERIAL_DURABILITY = {
    "stone": 300,
    "metal": 200,
    "parchment": 80,
    "wood": 60,
    "cloth": 40,
    "oral": 30,
}

MATERIAL_DECAY_RATE = {
    "stone": 0.2,
    "metal": 0.5,
    "parchment": 1.5,
    "wood": 2.0,
    "cloth": 2.5,
    "oral": 3.0,
}

# ---- LLM 参数 ----
LLM_MODEL_PATH = os.path.join(DATA_DIR, "model.gguf")
LLM_N_CTX = 4096
LLM_N_THREADS = 8
LLM_MAX_TOKENS = 512
LLM_TEMPERATURE = 0.7
LLM_TOP_P = 0.9

# ---- 缓存 ----
NARRATIVE_CACHE_MAX_ENTRIES = 10000

# ---- Phase 2: 经济与事件规则 ----
FOOD_PRODUCTION_BASE = {
    "river_valley": 120.0,
    "grassland": 100.0,
    "forest": 90.0,
    "plains": 85.0,
    "scrubland": 60.0,
    "highland": 50.0,
    "desert": 30.0,
    "tundra": 20.0,
    "mountain": 35.0,
}
FOOD_CONSUMPTION_PER_CAPITA = 10.0  # 每人每年
TAX_RATE_BASE = 0.15                  # 基础税率
MAINTENANCE_COST_PER_CAPITA = 0.5    # 每人每年公共支出

AMBIENT_EVENT_WEIGHT_REDUCTION = 0.3  # 旧随机事件概率乘以该因子
CAUSE_EVENT_LOOKBACK_YEARS = 5
MAX_EVENTS_PER_SETTLEMENT_PER_YEAR = 3

# ---- Phase 2: 调试 ----
DEBUG_CAUSES_MAX_CHAIN_DEPTH = 5
