"""Persistent informant identity, mortality, and knowledge tests."""

from game.repl import GameREPL
from simulation.informants import INFORMANT_ROLES
from simulation.world import World


def test_initial_settlements_have_mortal_persistent_informants():
    world = World(seed=42)
    world.generate(years=0)

    for settlement in world.settlements.values():
        informants = world.get_available_informants(settlement.id)
        assert {item.role for item in informants} == set(INFORMANT_ROLES)
        for informant in informants:
            person = world.persons[informant.person_id]
            assert person.alive
            assert person.settlement_id == settlement.id
            assert informant.role in person.roles


def test_dead_informants_are_replaced_but_not_resurrected():
    world = World(seed=42)
    world.generate(years=100)
    dead = [
        item for item in world.informants.values()
        if not world.persons[item.person_id].alive
    ]

    assert dead
    assert all(item not in world.get_available_informants(item.settlement_id)
               for item in dead)
    for settlement in world.settlements.values():
        active = world.get_available_informants(settlement.id)
        if settlement.alive:
            assert {item.role for item in active} == set(INFORMANT_ROLES)
            assert all(world.persons[item.person_id].alive for item in active)
        else:
            assert active == []


def test_knowledge_entries_belong_to_their_declared_holder():
    world = World(seed=42)
    world.generate(years=30)

    assert world.knowledge_entries
    for informant in world.informants.values():
        for entry_id in informant.known_entry_ids:
            entry = world.knowledge_entries[entry_id]
            assert entry.holder_id == informant.id
            assert entry.source_record_id in world.records
            assert entry.source_evidence_id in world.evidence
            assert entry.claim_ids


def test_inherited_knowledge_loses_certainty_and_tracks_parent():
    world = World(seed=42)
    world.generate(years=100)
    inherited = next(
        entry for entry in world.knowledge_entries.values()
        if entry.parent_entry_id is not None
    )
    parent = world.knowledge_entries[inherited.parent_entry_id]

    assert inherited.holder_id != parent.holder_id
    assert inherited.transmission_depth == parent.transmission_depth + 1
    assert inherited.certainty < parent.certainty
    assert inherited.source_root_id == parent.source_root_id


def test_informants_and_knowledge_are_deterministic_and_serializable():
    first = World(seed=19)
    first.generate(years=20)
    second = World(seed=19)
    second.generate(years=20)

    assert {
        key: value.to_dict() for key, value in first.informants.items()
    } == {
        key: value.to_dict() for key, value in second.informants.items()
    }
    assert {
        key: value.to_dict() for key, value in first.knowledge_entries.items()
    } == {
        key: value.to_dict() for key, value in second.knowledge_entries.items()
    }

    restored = World.from_dict(first.to_dict())
    assert {
        key: value.to_dict() for key, value in restored.informants.items()
    } == {
        key: value.to_dict() for key, value in first.informants.items()
    }
    assert {
        key: value.to_dict() for key, value in restored.knowledge_entries.items()
    } == {
        key: value.to_dict() for key, value in first.knowledge_entries.items()
    }


def test_legacy_world_builds_current_informants_and_knowledge():
    world = World(seed=31)
    world.generate(years=10)
    legacy = world.to_dict()
    legacy.pop("informants")
    legacy.pop("knowledge_entries")
    legacy["schema_version"] = 7

    restored = World.from_dict(legacy)

    assert restored.informants
    assert restored.knowledge_entries
    for settlement in restored.settlements.values():
        if settlement.alive:
            assert {item.role for item in restored.get_available_informants(
                settlement.id)} == set(INFORMANT_ROLES)


def test_villager_cannot_use_local_oral_records_the_elder_does_not_hold():
    world = World(seed=0)
    world.generate(years=22)
    trace = next(
        evidence for evidence in world.evidence.values()
        if evidence.evidence_type in {"artifact", "structure", "environmental"}
        and evidence.state != "destroyed"
        and world.get_available_informants(evidence.location_id, {"elder"})
        and any(
            oral.location_id == evidence.location_id
            and oral.evidence_type == "oral"
            and oral.state != "destroyed"
            for oral in world.evidence.values()
        )
    )
    elder = world.get_available_informants(trace.location_id, {"elder"})[0]
    elder.known_entry_ids.clear()
    local = world.get_all_visible_evidence(trace.location_id)
    index = local.index(trace) + 1
    repl = GameREPL(world)
    repl.current_location_id = trace.location_id
    repl.examined_evidence.add(trace.id)

    repl.cmd_present(f"{index} to villager")

    assert repl.knowledge.known_claims == {}
    result = next(iter(repl.knowledge.consultations.values()))
    assert result.matched_knowledge_ids == ()


def test_named_elder_consultation_uses_a_held_knowledge_entry():
    world = World(seed=42)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    elder = world.get_available_informants(settlement.id, {"elder"})[0]
    person = world.persons[elder.person_id]
    trace = next(
        evidence for evidence in world.get_all_visible_evidence(settlement.id)
        if evidence.evidence_type in {"artifact", "structure", "environmental"}
    )
    local = world.get_all_visible_evidence(settlement.id)
    index = local.index(trace) + 1
    repl = GameREPL(world)
    repl.current_location_id = settlement.id
    repl.examined_evidence.add(trace.id)

    repl.cmd_present(f"{index} to {person.name}")

    result = next(iter(repl.knowledge.consultations.values()))
    assert result.consultant_id == elder.id
    assert set(result.matched_knowledge_ids) <= set(elder.known_entry_ids)
    assert result.claim_statements
    assert all(item.speaker_id == elder.id for item in result.statements)


def test_artisan_does_not_turn_material_analysis_into_history(capsys):
    world = World(seed=42)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    artisan = world.get_available_informants(settlement.id, {"artisan"})[0]
    evidence = next(
        item for item in world.get_all_visible_evidence(settlement.id)
        if item.evidence_type in {"artifact", "structure"}
    )
    local = world.get_all_visible_evidence(settlement.id)
    index = local.index(evidence) + 1
    repl = GameREPL(world)
    repl.current_location_id = settlement.id
    repl.examined_evidence.add(evidence.id)

    repl.cmd_present(f"{index} to artisan")
    output = capsys.readouterr().out

    assert world.persons[artisan.person_id].name in output
    assert "材质、接合和磨损" in output
    assert repl.knowledge.known_claims == {}


def test_consultants_command_lists_only_current_living_people(capsys):
    world = World(seed=42)
    world.generate(years=30)
    settlement = next(item for item in world.settlements.values() if item.alive)
    active = world.get_available_informants(settlement.id)
    repl = GameREPL(world)
    repl.current_location_id = settlement.id

    repl.cmd_consultants()
    output = capsys.readouterr().out

    assert all(world.persons[item.person_id].name in output for item in active)
    assert all(world.persons[item.person_id].name not in output
               for item in world.informants.values()
               if item.settlement_id == settlement.id
               and not world.persons[item.person_id].alive)
