"""Pure planning logic for historically generated settlements."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from config import (
    DYNAMIC_FOUNDING_BASE_PROBABILITY,
    DYNAMIC_FOUNDING_COOLDOWN_YEARS,
    DYNAMIC_FOUNDING_ENABLED,
    DYNAMIC_FOUNDING_FOOD_MONTHS,
    DYNAMIC_FOUNDING_MAX_FOOD_SHORTAGE,
    DYNAMIC_FOUNDING_MAX_PROBABILITY,
    DYNAMIC_FOUNDING_MAX_SETTLERS,
    DYNAMIC_FOUNDING_MAX_WORLD_SETTLEMENTS,
    DYNAMIC_FOUNDING_MIN_DISTANCE,
    DYNAMIC_FOUNDING_MIN_LEGITIMACY,
    DYNAMIC_FOUNDING_MIN_SOURCE_POPULATION,
    DYNAMIC_FOUNDING_MIN_STABILITY,
    DYNAMIC_FOUNDING_MIN_SETTLERS,
    DYNAMIC_FOUNDING_MIN_SUITABILITY,
    DYNAMIC_FOUNDING_MIN_TREASURY,
    DYNAMIC_FOUNDING_SEARCH_RADIUS_BASE,
    DYNAMIC_FOUNDING_SETTLER_FRACTION,
    DYNAMIC_FOUNDING_SOURCE_POPULATION_RESERVE,
    DYNAMIC_FOUNDING_TREASURY_FRACTION,
    DYNAMIC_FOUNDING_MIN_YEAR,
    DYNAMIC_FOUNDING_PROBABILITY_SCALE,
)
from simulation.pressures import clamp


BLOCKED_FOUNDING_BIOMES = {"ocean", "lake", "river", "mountain"}
BIOME_AFFINITY = {
    "river_valley": 1.00,
    "grassland": 0.90,
    "forest": 0.78,
    "plains": 0.74,
    "scrubland": 0.48,
    "highland": 0.45,
    "desert": 0.25,
    "tundra": 0.22,
}


@dataclass(frozen=True)
class FoundingSiteCandidate:
    x: int
    y: int
    biome: str
    suitability: float
    distance_from_source: int
    nearest_settlement_distance: int
    travel_cost: float
    site_score: float


@dataclass(frozen=True)
class FoundingPlan:
    source_settlement_id: str
    x: int
    y: int
    biome: str
    settler_count: int
    food_transfer: float
    treasury_transfer: float
    founder_person_id: str
    controller_polity_id: str
    founding_type: str
    trigger_factors: dict[str, float]
    site_factors: dict[str, float]


def build_founding_site_context(world) -> tuple[
        frozenset[tuple[int, int]], list[list[int]]]:
    """Build one annual Manhattan-distance map shared by all source towns."""
    geography = world.geography
    if geography is None:
        return frozenset(), []

    occupied = frozenset(
        (int(settlement.grid_x), int(settlement.grid_y))
        for settlement in world.settlements.values()
    )
    unreachable = geography.width + geography.height
    distances = [
        [unreachable] * geography.width for _ in range(geography.height)
    ]
    queue = deque()
    for x, y in occupied:
        if 0 <= x < geography.width and 0 <= y < geography.height:
            distances[y][x] = 0
            queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        next_distance = distances[y][x] + 1
        for next_x, next_y in (
                (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (0 <= next_x < geography.width
                    and 0 <= next_y < geography.height
                    and next_distance < distances[next_y][next_x]):
                distances[next_y][next_x] = next_distance
                queue.append((next_x, next_y))

    return occupied, distances


def find_founding_sites(
        world, source, site_context=None) -> list[FoundingSiteCandidate]:
    geography = world.geography
    if geography is None:
        return []
    search_radius = DYNAMIC_FOUNDING_SEARCH_RADIUS_BASE + min(
        12, int(source.technology_level * 2))
    occupied, nearest_distances = (
        site_context if site_context is not None
        else build_founding_site_context(world)
    )
    candidates = []
    min_x = max(0, int(source.grid_x) - search_radius)
    max_x = min(geography.width - 1, int(source.grid_x) + search_radius)
    min_y = max(0, int(source.grid_y) - search_radius)
    max_y = min(geography.height - 1, int(source.grid_y) + search_radius)

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            distance = abs(x - source.grid_x) + abs(y - source.grid_y)
            if not DYNAMIC_FOUNDING_MIN_DISTANCE <= distance <= search_radius:
                continue
            suitability = float(geography.suitability[y, x])
            biome = str(geography.biomes[y, x])
            if (suitability < DYNAMIC_FOUNDING_MIN_SUITABILITY
                    or biome in BLOCKED_FOUNDING_BIOMES
                    or (x, y) in occupied):
                continue
            nearest = nearest_distances[y][x]
            if nearest < DYNAMIC_FOUNDING_MIN_DISTANCE:
                continue

            distance_score = 1.0 - clamp(
                (distance - DYNAMIC_FOUNDING_MIN_DISTANCE)
                / max(search_radius - DYNAMIC_FOUNDING_MIN_DISTANCE, 1))
            spacing_score = clamp(nearest / max(search_radius, 1))
            travel_cost = clamp(distance / max(search_radius, 1))
            site_score = (
                0.55 * suitability
                + 0.20 * distance_score
                + 0.15 * spacing_score
                + 0.10 * BIOME_AFFINITY.get(biome, 0.20)
            )
            candidates.append(FoundingSiteCandidate(
                x=x,
                y=y,
                biome=biome,
                suitability=suitability,
                distance_from_source=int(distance),
                nearest_settlement_distance=int(nearest),
                travel_cost=travel_cost,
                site_score=site_score,
            ))

    return sorted(candidates, key=lambda item: (
        -item.site_score, item.distance_from_source, item.y, item.x))


class SettlementFoundingPlanner:
    """Evaluate one source settlement without mutating the world."""

    def eligible(self, world, source, year: int) -> bool:
        polity = world.polities.get(source.controller_polity_id)
        last_year = world._last_founding_year.get(source.id)
        return bool(
            DYNAMIC_FOUNDING_ENABLED
            and year >= DYNAMIC_FOUNDING_MIN_YEAR
            and len(world.settlements)
            < DYNAMIC_FOUNDING_MAX_WORLD_SETTLEMENTS
            and source.alive
            and year > source.protected_until_year
            and source.population >= DYNAMIC_FOUNDING_MIN_SOURCE_POPULATION
            and source.stability >= DYNAMIC_FOUNDING_MIN_STABILITY
            and source.legitimacy >= DYNAMIC_FOUNDING_MIN_LEGITIMACY
            and source.food_shortage <= DYNAMIC_FOUNDING_MAX_FOOD_SHORTAGE
            and source.treasury >= DYNAMIC_FOUNDING_MIN_TREASURY
            and polity is not None
            and polity.alive
            and (last_year is None
                 or year - last_year >= DYNAMIC_FOUNDING_COOLDOWN_YEARS)
        )

    def probability(self, world, source,
                    best_site: FoundingSiteCandidate) -> tuple[float, dict]:
        population_factor = clamp(
            (source.population - DYNAMIC_FOUNDING_MIN_SOURCE_POPULATION)
            / 1000.0)
        expansion_pressure = world.get_pressure(
            source.id, "expansion_pressure")
        stability_factor = clamp(
            (source.stability - DYNAMIC_FOUNDING_MIN_STABILITY)
            / (1.0 - DYNAMIC_FOUNDING_MIN_STABILITY))
        treasury_factor = clamp(
            (source.treasury - DYNAMIC_FOUNDING_MIN_TREASURY) / 700.0)
        factors = {
            "population_factor": population_factor,
            "expansion_pressure": expansion_pressure,
            "stability_factor": stability_factor,
            "treasury_factor": treasury_factor,
            "site_factor": best_site.site_score,
        }
        raw_probability = (
            DYNAMIC_FOUNDING_BASE_PROBABILITY
            + 0.07 * population_factor
            + 0.05 * expansion_pressure
            + 0.03 * stability_factor
            + 0.03 * treasury_factor
            + 0.04 * best_site.site_score
        )
        probability = clamp(
            raw_probability * DYNAMIC_FOUNDING_PROBABILITY_SCALE,
            0.0,
            DYNAMIC_FOUNDING_MAX_PROBABILITY,
        )
        factors["raw_founding_probability"] = raw_probability
        factors["founding_probability"] = probability
        return probability, factors

    def may_attempt(self, world, source, year: int) -> bool:
        return bool(
            self.eligible(world, source, year)
            and self._roll(world, source, year)
            <= DYNAMIC_FOUNDING_MAX_PROBABILITY
            and self._founder_candidates(world, source, year)
        )

    def evaluate(
            self, world, source, year: int,
            site_context=None) -> FoundingPlan | None:
        if not self.eligible(world, source, year):
            return None
        founders = self._founder_candidates(world, source, year)
        if not founders:
            return None

        roll = self._roll(world, source, year)
        if roll > DYNAMIC_FOUNDING_MAX_PROBABILITY:
            return None

        sites = find_founding_sites(world, source, site_context)
        if not sites:
            return None
        probability, trigger_factors = self.probability(
            world, source, sites[0])
        if roll > probability:
            return None

        site = self._select_site(world, source, year, sites)
        founder = self._select_founder(world, source, year, founders)
        settler_count = min(
            max(
                round(source.population * DYNAMIC_FOUNDING_SETTLER_FRACTION),
                DYNAMIC_FOUNDING_MIN_SETTLERS,
            ),
            DYNAMIC_FOUNDING_MAX_SETTLERS,
            source.population - DYNAMIC_FOUNDING_SOURCE_POPULATION_RESERVE,
        )
        if settler_count < DYNAMIC_FOUNDING_MIN_SETTLERS:
            return None

        annual_need = settler_count * 10.0
        desired_food = annual_need * DYNAMIC_FOUNDING_FOOD_MONTHS / 12.0
        food_transfer = min(desired_food, source.food_stock * 0.35)
        source_minimum_food = source.population * 10.0 * 3.0 / 12.0
        if source.food_stock - food_transfer < source_minimum_food:
            return None
        treasury_transfer = min(
            source.treasury * DYNAMIC_FOUNDING_TREASURY_FRACTION, 120.0)
        if source.treasury - treasury_transfer < 100.0:
            return None

        return FoundingPlan(
            source_settlement_id=source.id,
            x=site.x,
            y=site.y,
            biome=site.biome,
            settler_count=int(settler_count),
            food_transfer=float(food_transfer),
            treasury_transfer=float(treasury_transfer),
            founder_person_id=founder.id,
            controller_polity_id=source.controller_polity_id,
            founding_type="planned_colony",
            trigger_factors=trigger_factors,
            site_factors={
                "site_suitability": site.suitability,
                "site_score": site.site_score,
                "site_travel_cost": site.travel_cost,
                "site_nearest_distance": float(
                    site.nearest_settlement_distance),
            },
        )

    @staticmethod
    def _roll(world, source, year: int) -> float:
        return random.Random(
            f"{world.seed}|founding_roll|{source.id}|{year}").random()

    @staticmethod
    def _founder_candidates(world, source, year: int) -> list:
        polity = world.polities[source.controller_polity_id]
        priorities = {"heir": 0, "general": 1, "merchant": 2, "artisan": 3}

        def priority(person):
            role_rank = min(
                (priorities[role] for role in person.roles
                 if role in priorities), default=4)
            return role_rank, person.id

        return sorted((
            person for person in world.persons.values()
            if person.alive
            and person.current_location_id == source.id
            and 22 <= person.age_at(year) <= 60
            and person.id != polity.ruler_id
            and person.id != source.ruler_id
            and not person.travel_role
        ), key=priority)

    @staticmethod
    def _select_site(world, source, year: int, sites):
        choices = sites[:5]
        rng = random.Random(
            f"{world.seed}|founding_site|{source.id}|{year}")
        return rng.choices(
            choices,
            weights=[max(item.site_score, 0.01) ** 3 for item in choices],
            k=1,
        )[0]

    @staticmethod
    def _select_founder(world, source, year: int, founders):
        best_rank = min(
            0 if "heir" in person.roles else
            1 if "general" in person.roles else
            2 if "merchant" in person.roles else
            3 if "artisan" in person.roles else 4
            for person in founders)
        choices = [
            person for person in founders
            if (0 if "heir" in person.roles else
                1 if "general" in person.roles else
                2 if "merchant" in person.roles else
                3 if "artisan" in person.roles else 4) == best_rank
        ]
        rng = random.Random(
            f"{world.seed}|founding_leader|{source.id}|{year}")
        return choices[rng.randrange(len(choices))]
