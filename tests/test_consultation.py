"""Truth-boundary and provenance tests for evidence consultation."""

import inspect
from functools import lru_cache

from game.consultation import ConsultationEngine
from game.investigation import (
    ClaimView,
    ConsultantView,
    ConsultationResult,
    EvidencePublicView,
    OralKnowledgeView,
    ReadingPublicView,
    RecordPublicView,
)
from game.knowledge import PlayerKnowledge
from narrative.document_reader import read_document
from simulation.world import World
from simulation.text_carriers import materialize_text_carrier


FORBIDDEN_TRUTH_FIELDS = {
    "event_id", "source_event_ids", "event_title", "event_details",
    "participants", "outcome_type", "created_year",
}


@lru_cache(maxsize=None)
def _document_case(seed=304):
    world = World(seed=seed)
    world.generate(years=0)
    evidence = next(
        item for item in world.evidence.values()
        if item.evidence_type == "document"
    )
    record = world.records[evidence.source_record_id]
    materialize_text_carrier(world, evidence.id)
    evidence_view = EvidencePublicView.from_evidence(evidence)
    record_view = RecordPublicView.from_record_and_evidence(record, evidence)
    reading_view = ReadingPublicView.from_result(
        read_document(evidence, {record.language_code}))
    consultant = ConsultantView(
        id="person_scholar", name="Meren", role="scholar",
        expertise=(("paleography", 0.8),),
        known_languages=(record.language_code,),
    )
    return evidence_view, record_view, reading_view, consultant


def test_public_views_exclude_truth_side_fields():
    evidence, record, _, _ = _document_case()

    assert FORBIDDEN_TRUTH_FIELDS.isdisjoint(evidence.to_dict())
    assert FORBIDDEN_TRUTH_FIELDS.isdisjoint(record.to_dict())
    assert all(FORBIDDEN_TRUTH_FIELDS.isdisjoint(claim)
               for claim in record.to_dict()["claims"])


def test_consultation_api_cannot_receive_world_or_event():
    parameters = set(inspect.signature(ConsultationEngine.consult).parameters)

    assert "world" not in parameters
    assert "event" not in parameters
    assert "events" not in parameters


def test_scholar_consultation_is_deterministic_and_serializable():
    evidence, record, reading, consultant = _document_case()
    engine = ConsultationEngine()

    first = engine.consult(evidence, consultant, reading, record)
    second = engine.consult(evidence, consultant, reading, record)
    restored = ConsultationResult.from_dict(first.to_dict())

    assert first == second
    assert restored == first
    assert first.claim_statements
    assert all("event_" not in statement.statement_cn
               for statement in first.statements)


def test_local_oral_match_uses_public_domain_and_location():
    evidence = EvidencePublicView(
        id="evd_trace", observed_name="带缺口的金属残片",
        evidence_type="artifact", material="metal", state="weathered",
        condition=0.6, location_id="stl_1",
        tags=("material:metal", "mark:impact_chips"),
        analysis_domains=("warfare", "craftsmanship"),
    )
    claim = ClaimView(
        subject="旧城", predicate="war_result", object="contested",
        statement_cn="当地歌谣声称交战双方都付出了代价。",
        time_range=(10, 14),
    )
    record = RecordPublicView(
        id="record_oral", source_root_id="record_oral",
        perspective="folk", language_code="common",
        record_type="oral_tradition", carrier_subtype="war_song",
        claims=(claim,),
    )
    local_memory = OralKnowledgeView(
        evidence_id="oral_1", location_id="stl_1", condition=0.8,
        domains=("warfare", "local_history"), record=record,
    )
    community = ConsultantView.local_community("stl_1")

    result = ConsultationEngine().consult(
        evidence, community, oral_knowledge=(local_memory,))

    assert result.matched_knowledge_ids == ("oral_1",)
    assert result.claim_statements[0].claim == claim
    assert "association_not_identity" in (
        result.claim_statements[0].uncertainty_codes)


def test_oral_memory_from_another_location_is_not_used():
    evidence = EvidencePublicView(
        id="evd_trace", observed_name="金属残片",
        evidence_type="artifact", material="metal", state="intact",
        condition=1.0, location_id="stl_1", tags=(),
        analysis_domains=("warfare",),
    )
    record = RecordPublicView(
        id="record_oral", source_root_id="record_oral",
        perspective="folk", language_code="common",
        record_type="oral_tradition", carrier_subtype="war_song",
        claims=(ClaimView(
            subject="远城", predicate="war_result", object="contested",
            statement_cn="远方流传着一则战争故事。", time_range=(5, 8)),),
    )
    remote_memory = OralKnowledgeView(
        evidence_id="oral_remote", location_id="stl_2", condition=1.0,
        domains=("warfare",), record=record,
    )

    result = ConsultationEngine().consult(
        evidence, ConsultantView.local_community("stl_1"),
        oral_knowledge=(remote_memory,))

    assert not result.claim_statements
    assert result.matched_knowledge_ids == ()


def test_repeated_consultation_does_not_inflate_player_knowledge():
    evidence, record, reading, consultant = _document_case()
    result = ConsultationEngine().consult(
        evidence, consultant, reading, record)
    knowledge = PlayerKnowledge()

    first = knowledge.learn_from_consultation(result)
    claim = first[0]
    first_confidence = claim.confidence
    second = knowledge.learn_from_consultation(result)

    assert first
    assert second == []
    assert claim.confidence == first_confidence
    assert len(claim.supporting_statement_ids) == 1
    assert len(knowledge.consultations) == 1


def test_changed_evidence_condition_creates_a_new_consultation_result():
    evidence, record, reading, consultant = _document_case()
    weathered = EvidencePublicView(
        id=evidence.id,
        observed_name=evidence.observed_name,
        evidence_type=evidence.evidence_type,
        material=evidence.material,
        state="weathered",
        condition=0.45,
        location_id=evidence.location_id,
        tags=evidence.tags,
        analysis_domains=evidence.analysis_domains,
    )
    engine = ConsultationEngine()

    intact_result = engine.consult(evidence, consultant, reading, record)
    weathered_result = engine.consult(weathered, consultant, reading, record)

    assert intact_result.id != weathered_result.id


def test_consultation_knowledge_roundtrip():
    evidence, record, reading, consultant = _document_case()
    result = ConsultationEngine().consult(
        evidence, consultant, reading, record)
    knowledge = PlayerKnowledge()
    knowledge.learn_from_consultation(result)

    restored = PlayerKnowledge.from_dict(knowledge.to_dict())

    assert restored.to_dict() == knowledge.to_dict()
