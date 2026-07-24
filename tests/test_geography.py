"""Geographic realism and determinism invariants."""

import numpy as np
import pytest

from config import MIN_SETTLEMENT_DISTANCE, SEA_LEVEL
from simulation.geography import Geography, pick_settlement_sites


@pytest.fixture(scope="module")
def geography():
    result = Geography(seed=42)
    result.generate()
    return result


def test_geography_is_deterministic():
    first = Geography(seed=77)
    second = Geography(seed=77)
    first.generate()
    second.generate()

    for layer in (
            "heightmap", "temperature", "rainfall", "rivers", "lakes",
            "flow_accumulation", "biomes", "suitability"):
        assert np.array_equal(getattr(first, layer), getattr(second, layer))
    assert [item.to_dict(include_cells=True) for item in first.features] == [
        item.to_dict(include_cells=True) for item in second.features]


def test_continuous_geographic_features_receive_unique_rule_based_names(
        geography):
    assert {"river", "mountain", "plains"} <= {
        item.feature_type for item in geography.features}
    names = [item.name for item in geography.features]
    assert len(names) == len(set(names))
    assert all(item.anchor in item.cells for item in geography.features)
    assert all(item.name_parts for item in geography.features)
    assert all(item.meaning_tags for item in geography.features)

    valid_biomes = {
        "river": {"river"},
        "lake": {"lake"},
        "mountain": {"mountain", "highland"},
        "plains": {"plains", "grassland"},
        "forest": {"forest"},
        "desert": {"desert", "scrubland"},
        "tundra": {"tundra"},
    }
    for feature in geography.features:
        assert all(
            str(geography.biomes[y, x])
            in valid_biomes[feature.feature_type]
            for x, y in feature.cells)
        assert geography.get_features_at(*feature.anchor)


def test_nearest_feature_lookup_respects_type_and_distance(geography):
    feature = next(
        item for item in geography.features if item.feature_type == "river")
    found = geography.nearest_features(
        *feature.anchor, {"river"}, max_distance=0.0, limit=1)

    assert found == [feature]
    assert not geography.nearest_features(
        *feature.anchor, {"mountain"}, max_distance=0.0, limit=1)


def test_continent_has_ocean_coast_and_varied_relief(geography):
    ocean = geography.heightmap <= SEA_LEVEL
    ocean_share = float(np.mean(ocean))
    edge = np.concatenate((
        ocean[0, :], ocean[-1, :], ocean[:, 0], ocean[:, -1],
    ))

    assert 0.15 < ocean_share < 0.50
    assert float(np.mean(edge)) > 0.65
    assert float(np.max(geography.heightmap)) > 0.9
    assert np.count_nonzero(geography.biomes == "mountain") > 100


def test_temperature_falls_with_elevation_at_similar_latitude(geography):
    y = geography.height // 2
    land = geography.heightmap[y] > SEA_LEVEL
    correlation = np.corrcoef(
        geography.heightmap[y][land], geography.temperature[y][land]
    )[0, 1]

    assert correlation < -0.75


def test_hydrology_produces_sparse_connected_high_flow_channels(geography):
    land = geography.heightmap > SEA_LEVEL
    rivers = geography.rivers.astype(bool)
    lakes = geography.lakes.astype(bool)

    assert 0.005 < float(np.mean(rivers)) < 0.06
    assert 0.0 < float(np.mean(lakes)) < 0.08
    assert not np.any(rivers & lakes)
    assert np.median(geography.flow_accumulation[rivers]) > \
        np.median(geography.flow_accumulation[land & ~rivers & ~lakes]) * 8

    water = rivers | lakes | ~land
    connected = 0
    river_cells = np.argwhere(rivers)
    for y, x in river_cells:
        neighbors = water[
            max(0, y - 1):min(geography.height, y + 2),
            max(0, x - 1):min(geography.width, x + 2),
        ]
        if np.count_nonzero(neighbors) > 1:
            connected += 1
    assert connected / len(river_cells) > 0.98


def test_biomes_distinguish_water_and_land(geography):
    assert np.all(geography.biomes[geography.heightmap <= SEA_LEVEL] == "ocean")
    assert np.all(geography.biomes[geography.lakes.astype(bool)] == "lake")
    assert np.all(geography.biomes[geography.rivers.astype(bool)] == "river")
    assert {
        "ocean", "lake", "river", "mountain", "highland",
        "river_valley", "forest", "grassland", "plains", "tundra",
    } <= set(geography.biomes.ravel())


def test_settlements_choose_spread_out_habitable_land(geography):
    sites = pick_settlement_sites(geography.suitability, 8, geography.seed)
    blocked = {"ocean", "lake", "river", "mountain"}

    assert len(sites) == 8
    for x, y in sites:
        assert geography.biomes[y, x] not in blocked
        assert geography.suitability[y, x] > 0.0
    for index, (x, y) in enumerate(sites):
        for other_x, other_y in sites[index + 1:]:
            assert abs(x - other_x) + abs(y - other_y) >= \
                MIN_SETTLEMENT_DISTANCE
