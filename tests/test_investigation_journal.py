"""Structured investigation journal and source-lineage tests."""

from game.investigation import (
    ClaimView,
    DocumentReading,
    EvidencePublicView,
    RecordPublicView,
    build_reading_statements,
)
from game.knowledge import PlayerKnowledge
from game.repl import GameREPL
from narrative.document_reader import read_document
from simulation.world import World


def _first_document(world):
    return next(
        item for item in world.evidence.values()
        if item.evidence_type == "document" and item.state != "destroyed")


def test_examine_records_objective_observations_without_duplicates(capsys):
    world = World(seed=410)
    world.generate(years=0)
    evidence = _first_document(world)
    local = world.get_all_visible_evidence(evidence.location_id)
    index = local.index(evidence) + 1
    repl = GameREPL(world)
    repl.current_location_id = evidence.location_id

    repl.cmd_examine(str(index))
    first_count = len(repl.knowledge.observations)
    repl.cmd_examine(str(index))
    capsys.readouterr()

    observations = list(repl.knowledge.observations.values())
    assert first_count >= 4
    assert len(observations) == first_count
    assert evidence.id in repl.knowledge.examined_evidence_ids
    assert all(item.evidence_id == evidence.id for item in observations)
    assert all("证明" not in item.description_cn for item in observations)
    assert all("历史事件" not in item.description_cn for item in observations)


def test_reading_persists_visible_text_and_sourced_statements(capsys):
    world = World(seed=411)
    world.generate(years=0)
    evidence = _first_document(world)
    record = world.records[evidence.source_record_id]
    local = world.get_all_visible_evidence(evidence.location_id)
    index = local.index(evidence) + 1
    repl = GameREPL(world)
    repl.current_location_id = evidence.location_id
    repl.known_languages.add(record.language_code)
    repl.examined_evidence.add(evidence.id)

    expected = read_document(evidence, repl.known_languages)
    repl.cmd_read(str(index))
    capsys.readouterr()

    reading = next(iter(repl.knowledge.document_readings.values()))
    assert reading.visible_passages == tuple(expected["visible_passages"])
    assert evidence.id in repl.knowledge.read_evidence_ids
    assert repl.knowledge.source_statements
    assert all(
        item.speaker_type == "player_reading"
        for item in repl.knowledge.source_statements.values())
    assert repl.knowledge.source_groups


def test_original_and_copy_share_one_source_group():
    claim = ClaimView(
        subject="Stoneford", predicate="war_result", object="contested",
        statement_cn="文书声称战斗没有明确胜者。", time_range=(12, 14))
    original_record = RecordPublicView(
        id="record_original", source_root_id="record_original",
        perspective="official", language_code="common",
        record_type="chronicle", carrier_subtype="war_record",
        claims=(claim,))
    copy_record = RecordPublicView(
        id="record_copy", source_root_id="record_original",
        perspective="official", language_code="common",
        record_type="chronicle", carrier_subtype="war_record_copy",
        claims=(claim,))
    original = EvidencePublicView(
        id="evidence_original", observed_name="旧编年册",
        evidence_type="document", material="parchment", state="intact",
        condition=0.9, location_id="stl_1", tags=(),
        analysis_domains=("paleography",))
    copied = EvidencePublicView(
        id="evidence_copy", observed_name="编年册抄本",
        evidence_type="document", material="parchment", state="intact",
        condition=0.8, location_id="stl_2", tags=(),
        analysis_domains=("paleography",))
    first_reading = DocumentReading.from_result(
        original.id, original.location_id, {
            "status": "readable", "language_code": "common",
            "readability": 1.0, "visible_passages": ["原件文字"],
        })
    second_reading = DocumentReading.from_result(
        copied.id, copied.location_id, {
            "status": "readable", "language_code": "common",
            "readability": 1.0, "visible_passages": ["抄本文字"],
        })
    knowledge = PlayerKnowledge()

    knowledge.record_reading(
        first_reading,
        build_reading_statements(original, first_reading, original_record))
    knowledge.record_reading(
        second_reading,
        build_reading_statements(copied, second_reading, copy_record))

    known = next(iter(knowledge.known_claims.values()))
    group = next(iter(knowledge.source_groups.values()))
    assert len(knowledge.source_groups) == 1
    assert len(known.source_groups) == 1
    assert set(group.evidence_ids) == {original.id, copied.id}
    assert len(group.statement_ids) == 2


def test_journal_can_show_each_category(capsys):
    world = World(seed=412)
    world.generate(years=0)
    repl = GameREPL(world)

    for section, heading in (
        ("observations", "客观观察"),
        ("texts", "文书原文"),
        ("statements", "他人说法"),
        ("claims", "综合主张"),
        ("conflicts", "未解决冲突"),
    ):
        repl.cmd_journal(section)
        assert heading in capsys.readouterr().out


def test_phase_c_knowledge_roundtrip():
    world = World(seed=413)
    world.generate(years=0)
    evidence = _first_document(world)
    result = read_document(
        evidence, {world.records[evidence.source_record_id].language_code})
    evidence_view = EvidencePublicView.from_evidence(evidence)
    record_view = RecordPublicView.from_record_and_evidence(
        world.records[evidence.source_record_id], evidence)
    reading = DocumentReading.from_result(
        evidence.id, evidence.location_id, result)
    knowledge = PlayerKnowledge()
    knowledge.record_reading(
        reading, build_reading_statements(
            evidence_view, reading, record_view))

    restored = PlayerKnowledge.from_dict(knowledge.to_dict())

    assert restored.to_dict() == knowledge.to_dict()
