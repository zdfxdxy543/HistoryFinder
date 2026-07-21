"""Confidence components, temporal conflicts, and evidence comparison."""

import inspect

import pytest

from game.comparison import ComparisonEngine
from game.investigation import (
    ClaimView,
    ComparisonResult,
    EvidencePublicView,
    Observation,
    SourceStatement,
)
from game.knowledge import (
    CONFIDENCE_COMPONENT_KEYS,
    PlayerKnowledge,
)
from game.repl import GameREPL
from simulation.world import World


def _statement(identifier: str, object_value: str,
               time_range: tuple[int, int], group_id: str,
               predicate: str = "war_result",
               transmission_depth: int = 0) -> SourceStatement:
    claim = ClaimView(
        subject="Stoneford",
        predicate=predicate,
        object=object_value,
        statement_cn=f"一份记录声称结果为 {object_value}。",
        time_range=time_range,
    )
    return SourceStatement(
        id=identifier,
        speaker_type="player_reading",
        speaker_id="player",
        presented_evidence_id=f"evidence_{identifier}",
        source_evidence_id=f"evidence_{identifier}",
        source_record_root_id=f"record_{group_id}",
        statement_type="document_transcription",
        statement_cn=claim.statement_cn,
        claim=claim,
        perspective="official",
        carrier_condition=0.8,
        comprehension=0.9,
        source_group_id=group_id,
        transmission_depth=transmission_depth,
    )


def _evidence(identifier: str, material: str = "metal",
              condition: float = 0.8) -> EvidencePublicView:
    return EvidencePublicView(
        id=identifier,
        observed_name=identifier,
        evidence_type="artifact",
        material=material,
        state="intact" if condition >= 0.7 else "weathered",
        condition=condition,
        location_id="stl_1",
        tags=(),
        analysis_domains=("craftsmanship",),
    )


def test_overlapping_exclusive_claims_create_strong_conflict():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement("statement_a", "attacker_victory", (10, 14), "group_a"),
        _statement("statement_b", "defender_victory", (12, 16), "group_b"),
    ])

    assert len(knowledge.conflicts) == 1
    conflict = next(iter(knowledge.conflicts.values()))
    assert conflict.relation_type == "exclusive"
    assert conflict.strength == "strong"
    assert conflict.overlap_range == (12, 14)
    assert all(
        claim.confidence_components["contradiction"] == -0.12
        for claim in knowledge.known_claims.values())


def test_same_topic_in_different_years_is_not_a_conflict():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement("statement_a", "attacker_victory", (10, 12), "group_a"),
        _statement("statement_b", "defender_victory", (30, 32), "group_b"),
    ])

    assert knowledge.conflicts == {}
    assert all(
        not claim.contradicting_evidence_ids
        for claim in knowledge.known_claims.values())


def test_compatible_predicate_is_not_auto_conflicted():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement(
            "statement_a", "Song of Ash", (10, 12), "group_a",
            predicate="authored_work"),
        _statement(
            "statement_b", "Song of Rain", (10, 12), "group_b",
            predicate="authored_work"),
    ])

    assert knowledge.conflicts == {}


def test_confidence_components_count_copy_lineage_once():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement("statement_original", "contested", (10, 12), "group_a"),
        _statement("statement_copy", "contested", (10, 12), "group_a"),
    ])

    claim = next(iter(knowledge.known_claims.values()))
    assert set(claim.confidence_components) == set(CONFIDENCE_COMPONENT_KEYS)
    assert claim.confidence_components["source_independence"] == 0.16
    assert len(claim.source_groups) == 1


def test_transmission_depth_has_visible_penalty():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement(
            "statement_oral", "contested", (10, 12), "oral_group",
            transmission_depth=3),
    ])

    claim = next(iter(knowledge.known_claims.values()))
    assert claim.confidence_components["transmission_penalty"] == pytest.approx(
        -0.09)


def test_comparison_is_deterministic_symmetric_and_truth_isolated():
    first = _evidence("evidence_a", "metal", 0.82)
    second = _evidence("evidence_b", "metal", 0.76)
    first_observation = Observation.create(
        first, "mark", "parallel_scratches", "表面有数道平行刮痕。")
    second_observation = Observation.create(
        second, "mark", "parallel_scratches", "表面有数道平行刮痕。")
    engine = ComparisonEngine()

    forward = engine.compare(
        first, second, (first_observation,), (second_observation,),
        ("shared_group",), ("shared_group",))
    reverse = engine.compare(
        second, first, (second_observation,), (first_observation,),
        ("shared_group",), ("shared_group",))
    restored = ComparisonResult.from_dict(forward.to_dict())

    assert forward == reverse
    assert restored == forward
    assert forward.source_group_relation == "same"
    assert any("不能算作两个独立来源" in item
               for item in forward.limitations_cn)
    parameters = set(inspect.signature(engine.compare).parameters)
    assert {"world", "event", "events"}.isdisjoint(parameters)


def test_repl_compare_requires_examination_and_records_result(capsys):
    world = World(seed=414)
    world.generate(years=0)
    settlement_id, evidence = next(
        (settlement_id, items)
        for settlement_id in world.settlements
        if len(items := world.get_all_visible_evidence(settlement_id)) >= 2)
    repl = GameREPL(world)
    repl.current_location_id = settlement_id

    repl.cmd_compare("1 with 2")
    assert "需要先 examine" in capsys.readouterr().out

    repl.cmd_examine("1")
    repl.cmd_examine("2")
    capsys.readouterr()
    repl.cmd_compare("1 with 2")
    output = capsys.readouterr().out

    assert "相同点" in output
    assert "差异点" in output
    assert "限制" in output
    assert len(repl.knowledge.comparisons) == 1
    assert set(next(iter(repl.knowledge.comparisons.values())).evidence_ids) == {
        evidence[0].id, evidence[1].id}


def test_reliability_state_roundtrip():
    knowledge = PlayerKnowledge()
    knowledge.learn_from_statements([
        _statement("statement_a", "attacker_victory", (10, 14), "group_a"),
        _statement("statement_b", "defender_victory", (12, 16), "group_b"),
    ])
    first = _evidence("evidence_a")
    second = _evidence("evidence_b", "stone", 0.5)
    comparison = ComparisonEngine().compare(first, second)
    knowledge.record_comparison(comparison)

    restored = PlayerKnowledge.from_dict(knowledge.to_dict())

    assert restored.to_dict() == knowledge.to_dict()
