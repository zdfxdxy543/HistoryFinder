"""Record, evidence, and player-knowledge separation tests."""

import pytest

from game.knowledge import PlayerKnowledge
from game.repl import GameREPL
from simulation.events import HistoricalEvent
from simulation.person import Person
from simulation.records import Claim, HistoricalRecord
from simulation.world import World
from simulation.text_carriers import has_text_carrier


@pytest.fixture(scope="module")
def recorded_world():
    world = World(seed=0)
    world.generate(years=30)
    return world


def test_claim_and_record_roundtrip():
    claim = Claim(
        id="record_1:claim:1", subject="Redhaven",
        predicate="war_result", object="contested",
        statement_cn="一份歌谣声称战斗结局存在争议。",
        time_range=(10, 14), qualifiers=["date_approximate"],
    )
    record = HistoricalRecord(
        id="record_1", source_event_ids=["event_1"],
        created_year=12, created_location_id="stl_1",
        record_type="oral_tradition", claimed_facts=[claim],
        perspective="folk", intended_audience="local_community",
        carrier_subtype="war_song",
        distortions=["approximate_date"],
    )

    restored = HistoricalRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.claimed_facts[0].semantic_key() == claim.semantic_key()


def test_generated_records_have_multiple_perspectives(recorded_world):
    war = next(
        event for event in recorded_world.events
        if event.event_type == "war"
    )
    records = [
        record for record in recorded_world.records.values()
        if war.id in record.source_event_ids and record.copy_parent_id is None
    ]

    assert {record.perspective for record in records} >= {"official", "folk"}
    claims = [record.claimed_facts[0] for record in records]
    assert len({claim.topic_key() for claim in claims}) == 1
    assert len({claim.object for claim in claims}) >= 2
    assert any(record.distortions for record in records
               if record.perspective == "folk")


def test_record_carriers_do_not_copy_event_truth(recorded_world):
    carriers = [
        evidence for evidence in recorded_world.evidence.values()
        if (evidence.evidence_type in {"document", "oral"}
            or has_text_carrier(evidence))
    ]
    traces = [
        evidence for evidence in recorded_world.evidence.values()
        if (evidence.evidence_type
            in {"artifact", "structure", "environmental"}
            and not has_text_carrier(evidence))
    ]

    assert carriers and traces
    assert all(evidence.source_record_id in recorded_world.records
               for evidence in carriers)
    assert all(evidence.retained_claim_ids for evidence in carriers)
    assert all("event_details" not in evidence.content_data
               for evidence in recorded_world.evidence.values())
    assert all("event_title" not in evidence.content_data
               for evidence in recorded_world.evidence.values())
    assert all(evidence.source_record_id is None for evidence in traces)


def test_copied_documents_are_not_independent_sources(recorded_world):
    original = next(
        evidence for evidence in recorded_world.evidence.values()
        if evidence.evidence_type == "document"
        and evidence.is_copy_of is None
        and any(copy.is_copy_of == evidence.id
                for copy in recorded_world.evidence.values())
    )
    copied = next(
        evidence for evidence in recorded_world.evidence.values()
        if evidence.is_copy_of == original.id
    )
    original_record = recorded_world.records[original.source_record_id]
    copy_record = recorded_world.records[copied.source_record_id]
    knowledge = PlayerKnowledge()

    first = knowledge.learn_from_record(
        original_record, original, comprehension=1.0)
    second = knowledge.learn_from_record(
        copy_record, copied, comprehension=1.0)
    known = second[0]

    assert first
    assert copy_record.copy_parent_id == original_record.id
    assert copied.authenticity == "copy"
    assert len(known.supporting_evidence_ids) == 2
    assert known.source_record_roots == [original_record.id]


def test_conflicting_records_are_kept_as_conflicting_claims(recorded_world):
    war = next(
        event for event in recorded_world.events
        if event.event_type == "war"
    )
    carriers = [
        evidence for evidence in recorded_world.evidence.values()
        if war.id in evidence.source_event_ids
        and evidence.source_record_id is not None
        and recorded_world.records[evidence.source_record_id].copy_parent_id is None
    ]
    official = next(
        evidence for evidence in carriers
        if recorded_world.records[evidence.source_record_id].perspective == "official"
    )
    folk = next(
        evidence for evidence in carriers
        if recorded_world.records[evidence.source_record_id].perspective == "folk"
    )
    knowledge = PlayerKnowledge()

    knowledge.learn_from_record(
        recorded_world.records[official.source_record_id], official, 1.0)
    knowledge.learn_from_record(
        recorded_world.records[folk.source_record_id], folk, 1.0)
    claims = [
        claim for claim in knowledge.sorted_claims()
        if claim.predicate == "war_result"
    ]

    assert len(claims) == 2
    assert all(claim.contradicting_evidence_ids for claim in claims)
    assert {claim.object for claim in claims} == {
        war.details["outcome"], "contested",
    }


def test_reading_adds_claims_but_never_confirms_source_event(
        recorded_world, capsys):
    document = next(
        evidence for evidence in recorded_world.evidence.values()
        if evidence.evidence_type == "document" and evidence.state == "intact"
    )
    local = recorded_world.get_all_visible_evidence(document.location_id)
    index = local.index(document) + 1
    repl = GameREPL(recorded_world)
    repl.current_location_id = document.location_id
    repl.examined_evidence.add(document.id)

    repl.cmd_read(str(index))
    output = capsys.readouterr().out

    assert repl.knowledge.known_claims
    assert repl.known_events == set()
    assert "记入游记的主张" in output
    assert "event_" not in output


def test_presenting_to_scholar_interprets_record_not_truth(capsys):
    world = World(seed=304)
    world.generate(years=0)
    document = next(
        evidence for evidence in world.evidence.values()
        if evidence.evidence_type == "document"
    )
    scholar = Person(
        id="person_test_scholar", name="Meren", birth_year=-30,
        settlement_id=document.location_id, roles=["scholar"],
    )
    world.persons[scholar.id] = scholar
    local = world.get_all_visible_evidence(document.location_id)
    index = local.index(document) + 1
    repl = GameREPL(world)
    repl.current_location_id = document.location_id
    repl.examined_evidence.add(document.id)

    repl.cmd_present(f"{index} to scholar")
    output = capsys.readouterr().out

    assert "Meren辨认出的只是记录本身的主张" in output
    assert repl.knowledge.known_claims
    assert repl.known_events == set()
    assert "source_event" not in output


def test_villager_can_connect_traces_to_an_oral_claim(capsys):
    recorded_world = World(seed=6)
    recorded_world.generate(years=0)
    attacker, defender = list(recorded_world.settlements.values())[:2]
    war = HistoricalEvent(
        id="event_oral_war_test",
        year=1,
        event_type="war",
        title=f"{attacker.name}与{defender.name}交战",
        severity=0.7,
        primary_location=attacker.id,
        participants=[attacker.id, defender.id],
        details={
            "attacker": attacker.name,
            "defender": defender.name,
            "outcome": "stalemate",
        },
    )
    recorded_world._add_event_with_evidence(war)
    trace = next(
        evidence for evidence in recorded_world.evidence.values()
        if war.id in evidence.source_event_ids
        and evidence.evidence_type in {"artifact", "structure", "environmental"}
        and evidence.state != "destroyed"
    )
    local = recorded_world.get_all_visible_evidence(trace.location_id)
    index = local.index(trace) + 1
    repl = GameREPL(recorded_world)
    repl.current_location_id = trace.location_id
    repl.examined_evidence.add(trace.id)

    repl.cmd_present(f"{index} to villager")
    output = capsys.readouterr().out

    assert "这只是其所知版本" in output
    assert repl.knowledge.known_claims
    assert repl.known_events == set()
    assert "event_" not in output


def test_world_records_roundtrip(recorded_world):
    restored = World.from_dict(recorded_world.to_dict())

    assert set(restored.records) == set(recorded_world.records)
    for record_id, record in recorded_world.records.items():
        assert restored.records[record_id].to_dict() == record.to_dict()
    for evidence_id, evidence in recorded_world.evidence.items():
        assert (restored.evidence[evidence_id].source_record_id
                == evidence.source_record_id)


def test_world_rejects_missing_record_state():
    world = World(seed=305)
    world.generate(years=0)
    data = world.to_dict()
    data.pop("records")
    for evidence in data["evidence"]:
        evidence.pop("source_record_id", None)
        evidence.pop("retained_claim_ids", None)

    with pytest.raises(ValueError, match="missing: records"):
        World.from_dict(data)


def test_player_knowledge_roundtrip(recorded_world):
    evidence = next(
        item for item in recorded_world.evidence.values()
        if item.source_record_id is not None
    )
    record = recorded_world.records[evidence.source_record_id]
    knowledge = PlayerKnowledge()
    knowledge.discover_evidence(evidence.id)
    knowledge.learn_from_record(record, evidence, comprehension=1.0)

    restored = PlayerKnowledge.from_dict(knowledge.to_dict())

    assert restored.to_dict() == knowledge.to_dict()
