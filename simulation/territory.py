"""Derived current-control territory overlays for map presentation."""

from __future__ import annotations

from collections import deque


TERRITORY_INFLUENCE_RADIUS = 26


def build_territory_payload(
        world, terrain: list[list[int]], biome_codes: dict[str, int]) -> dict:
    """Derive current political influence without mutating simulation truth."""
    active_polity_ids = sorted({
        settlement.controller_polity_id
        for settlement in world.settlements.values()
        if settlement.alive
        and settlement.controller_polity_id in world.polities
    })
    polity_codes = {
        polity_id: code for code, polity_id in enumerate(active_polity_ids)
    }
    height = len(terrain)
    width = len(terrain[0]) if height else 0
    unclaimed = -1
    owners = [[unclaimed] * width for _ in range(height)]
    distances = [[TERRITORY_INFLUENCE_RADIUS + 1] * width
                 for _ in range(height)]
    queue = deque()

    for settlement in sorted(
            world.settlements.values(), key=lambda item: item.id):
        if not settlement.alive:
            continue
        code = polity_codes.get(settlement.controller_polity_id)
        if code is None:
            continue
        x, y = int(settlement.grid_x), int(settlement.grid_y)
        owners[y][x] = code
        distances[y][x] = 0
        queue.append((x, y))

    blocked = {biome_codes["ocean"], biome_codes["lake"]}
    while queue:
        x, y = queue.popleft()
        next_distance = distances[y][x] + 1
        if next_distance > TERRITORY_INFLUENCE_RADIUS:
            continue
        owner = owners[y][x]
        for next_x, next_y in (
                (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= next_x < width and 0 <= next_y < height):
                continue
            if terrain[next_y][next_x] in blocked:
                continue
            current_distance = distances[next_y][next_x]
            current_owner = owners[next_y][next_x]
            if (next_distance < current_distance
                    or (next_distance == current_distance
                        and (current_owner == unclaimed
                             or owner < current_owner))):
                distances[next_y][next_x] = next_distance
                owners[next_y][next_x] = owner
                queue.append((next_x, next_y))

    polities = []
    for polity_id in active_polity_ids:
        polity = world.polities[polity_id]
        controlled = sorted(
            settlement.id for settlement in world.settlements.values()
            if settlement.alive
            and settlement.controller_polity_id == polity_id
        )
        polities.append({
            "id": polity.id,
            "code": polity_codes[polity_id],
            "name": polity.name,
            "capital_settlement_id": polity.capital_settlement_id,
            "settlement_ids": controlled,
        })

    return {
        "basis": "derived_current_control",
        "influence_radius": TERRITORY_INFLUENCE_RADIUS,
        "unclaimed_code": unclaimed,
        "owners": owners,
        "polities": polities,
    }
