import random

from simulation.world import World


def test_destroyed_settlement_stops_participating_in_diplomatic_chains():
    world = World(seed=42)
    world.generate(years=0)
    living, ruin = list(world.settlements.values())[:2]
    ruin.alive = False
    ruin.destroyed_year = 5
    world._pending_war_settlements = [(living.id, 4, ruin.id)]

    for year in range(6, 25):
        world.current_year = year
        alive = [
            item for item in world.settlements.values() if item.alive]
        world._process_event_chains(year, alive, random.Random(4200 + year))
    later_diplomacy = [
        event for event in world.events
        if event.year > ruin.destroyed_year
        and ruin.id in event.participants
        and event.event_type in {"trade", "war", "raid", "treaty"}
    ]
    assert later_diplomacy == []


def test_destroyed_treaty_side_is_not_attached_as_a_signing_office():
    world = World(seed=42)
    world.generate(years=0)
    living, ruin = list(world.settlements.values())[:2]
    ruin.alive = False
    ruin.destroyed_year = 5
    event = world._event_gen.generate_treaty_event(
        6, ruin.id, ruin.name, living.id, living.name,
        living.id, "peace")

    world._attach_current_rulers(event)

    assert len(event.person_ids) == 1
    assert event.person_ids == [living.ruler_id]
