"""Persistent person identity, mortality, and succession tests."""

from simulation.world import World


def test_initial_rulers_and_heirs_are_real_people():
    world = World(seed=42)
    world.generate(years=0)

    for settlement in world.settlements.values():
        ruler = world.get_person(settlement.ruler_id)
        assert ruler is not None and ruler.alive
        assert ruler.name == settlement.ruler_name
        assert "ruler" in ruler.roles
        heirs = [
            person for person in world.persons.values()
            if person.alive and person.settlement_id == settlement.id
            and "heir" in person.roles
        ]
        assert heirs


def test_people_are_deterministic_for_the_same_seed():
    first = World(seed=42)
    first.generate(years=60)
    second = World(seed=42)
    second.generate(years=60)

    assert {
        person_id: person.to_dict()
        for person_id, person in first.persons.items()
    } == {
        person_id: person.to_dict()
        for person_id, person in second.persons.items()
    }


def test_succession_connects_dead_rulers_to_real_successors():
    world = World(seed=42)
    world.generate(years=100)
    successions = [
        event for event in world.events
        if event.event_type == "ruler_change"
        and event.details.get("old_ruler_id")
    ]

    assert successions
    for event in successions:
        old_ruler = world.get_person(event.details["old_ruler_id"])
        new_ruler = world.get_person(event.details["new_ruler_id"])
        assert old_ruler is not None and new_ruler is not None
        assert old_ruler.death_year == event.year
        assert new_ruler.birth_year <= event.year
        assert old_ruler.name == event.details["old_ruler"]
        assert new_ruler.name == event.details["new_ruler"]
        assert event.person_ids == [old_ruler.id, new_ruler.id]

    for settlement in world.settlements.values():
        if not settlement.alive:
            continue
        ruler = world.get_person(settlement.ruler_id)
        assert ruler is not None and ruler.alive
        assert ruler.name == settlement.ruler_name


def test_events_never_reference_people_after_their_death():
    world = World(seed=42)
    world.generate(years=100)

    for event in world.events:
        for person_id in event.person_ids:
            person = world.get_person(person_id)
            assert person is not None
            assert person.death_year is None or event.year <= person.death_year


def test_wars_treaties_discoveries_and_rebellions_reference_people():
    world = World(seed=42)
    world.generate(years=100)

    wars = [event for event in world.events if event.event_type == "war"]
    treaties = [event for event in world.events if event.event_type == "treaty"]
    discoveries = [
        event for event in world.events if event.event_type == "discovery"
    ]
    assert wars and treaties and discoveries
    assert all(len(event.details.get("commander_ids", [])) == 2 for event in wars)
    assert all(event.person_ids for event in wars + treaties + discoveries)
    assert all(len(event.person_ids) == len(set(event.person_ids)) == 2
               for event in treaties)

    rebellion_world = World(seed=2)
    rebellion_world.generate(years=40)
    rebellions = [
        event for event in rebellion_world.events
        if event.event_type == "rebellion"
    ]
    assert rebellions
    assert all(event.details.get("rebel_leader_id")
               for event in rebellions)


def test_successful_coup_promotes_the_same_rebel_leader():
    world = World(seed=7)
    world.generate(years=23)
    coup = next(
        event for event in world.events
        if event.event_type == "rebellion"
        and event.details.get("outcome_type") == "ruler_overthrown"
    )
    leader_id = coup.details["rebel_leader_id"]
    settlement = world.get_settlement(coup.primary_location)
    leader = world.get_person(leader_id)

    assert coup.details["new_ruler_id"] == leader_id
    assert settlement.ruler_id == leader_id
    assert settlement.ruler_name == leader.name
    assert leader.alive and "ruler" in leader.roles
