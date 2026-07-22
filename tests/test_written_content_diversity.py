"""Generation-time guarantees against accidental document duplication."""

from itertools import combinations

import pytest

from simulation.world import World
from simulation.text_carriers import materialize_text_carrier


@pytest.fixture(scope="module")
def written_world():
    world = World(seed=42)
    world.generate(years=100)
    for evidence in world.evidence.values():
        if (evidence.evidence_type == "document"
                and evidence.content_data.get("text_plan")):
            materialize_text_carrier(world, evidence.id)
    return world


def _documents(world):
    return [
        evidence for evidence in world.evidence.values()
        if evidence.evidence_type == "document"
        and "written_content" in evidence.content_data
    ]


def _full_text(evidence):
    return "\n".join(
        passage["text"]
        for passage in evidence.content_data["written_content"]["passages"]
    )


def _body_texts(evidence):
    return {
        passage["text"]
        for passage in evidence.content_data["written_content"]["passages"]
        if passage["kind"] not in {
            "heading", "attribution", "closing", "copy_note",
        }
    }


def _average_pair_overlap(items):
    overlaps = []
    for first, second in combinations(items, 2):
        first_body = _body_texts(first)
        second_body = _body_texts(second)
        overlaps.append(
            len(first_body & second_body) /
            max(1, len(first_body | second_body))
        )
    return sum(overlaps) / len(overlaps) if overlaps else 0.0


def test_every_generated_document_carrier_has_unique_full_wording(written_world):
    documents = _documents(written_world)

    assert len({_full_text(item) for item in documents}) == len(documents)


def test_generated_carriers_do_not_expose_generator_guidance_or_role_codes(
        written_world):
    forbidden = (
        "人物名册曾记录的身份包括", "人物记录中先后出现的身份包括",
        "当时的摘要为", "此句只记录", "共引用",
        "未记录的行动不列为功绩", "不等同于墓主本人的陈述",
        "正文记录到", "本页说明", "不是作品正文",
        "founder", "ruler", "general", "scholar", "writer", "heir",
    )
    for evidence in written_world.evidence.values():
        written = evidence.content_data.get("written_content")
        if not written:
            continue
        text = "\n".join(
            passage["text"] for passage in written["passages"])
        assert all(marker not in text for marker in forbidden), (
            evidence.id, evidence.subtype, text)


def test_copies_are_derived_with_visible_transmission_variation(written_world):
    copies = [item for item in _documents(written_world) if item.is_copy_of]

    assert copies
    for item in copies:
        parent = written_world.evidence[item.is_copy_of]
        passages = item.content_data["written_content"]["passages"]
        assert _full_text(item) != _full_text(parent)
        assert any(passage["kind"] == "copy_note" for passage in passages)
        assert any(passage["kind"] == "marginalia"
                   or "母本此处缺损" in passage["text"]
                   for passage in passages)


@pytest.mark.parametrize("genre", ["chronicle", "biography"])
def test_grounded_literature_keeps_distinct_full_text_without_filler(
        written_world, genre):
    events = {event.id: event for event in written_world.events}
    works = [
        item for item in _documents(written_world)
        if not item.is_copy_of
        and item.subtype == "literary_manuscript"
        and events[item.event_id].details.get("genre") == genre
    ]

    assert len(works) >= 2
    assert len({_full_text(work) for work in works}) == len(works)
    assert all(marker not in _full_text(work) for work in works for marker in (
        "编排说明", "人物说明", "地点说明", "年份说明",
        "来源说明", "增补说明", "综合上述记录", "后续版本",
    ))


@pytest.mark.parametrize("field", [
    "mechanics", "agronomy", "medicine", "astronomy",
])
def test_independent_theory_does_not_reuse_most_body_paragraphs(
        written_world, field):
    events = {event.id: event for event in written_world.events}
    works = [
        item for item in _documents(written_world)
        if not item.is_copy_of
        and item.subtype == "theoretical_treatise"
        and events[item.event_id].details.get("theory_field") == field
    ]

    assert len(works) >= 2
    assert _average_pair_overlap(works) < 0.25


def test_traveling_literary_copy_is_not_mistaken_for_copy_suffix(
        written_world):
    traveling_originals = [
        item for item in _documents(written_world)
        if not item.is_copy_of and item.subtype == "traveling_literary_copy"
    ]

    assert traveling_originals
    for item in traveling_originals:
        passages = item.content_data["written_content"]["passages"]
        assert len(passages) >= 4
        assert passages[0]["text"].startswith("《")
        assert any(passage["kind"] == "copy_note" for passage in passages)


def test_rule_documents_receive_specific_outcome_fields(written_world):
    events = {event.id: event for event in written_world.events}
    construction_records = [
        item for item in _documents(written_world)
        if not item.is_copy_of and item.subtype == "construction_record"
    ]

    assert construction_records
    for item in construction_records:
        event = events[item.event_id]
        heading = item.content_data["written_content"]["passages"][0]["text"]
        assert event.details["building_type"] == event.details["outcome_type"]
        assert "一处公共建筑" not in heading
