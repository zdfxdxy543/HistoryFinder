"""Lazy text families, copy transmission, and persistent damage."""

from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

from game.knowledge import PlayerKnowledge
from narrative.document_reader import read_document
from simulation.text_carriers import (
    advance_text_damage,
    materialize_text_carrier,
    render_damaged_passages,
)
from simulation.world import World


def _copy_case(seed=42):
    world = World(seed=seed)
    world.generate(years=0)
    copied = next(
        evidence for evidence in world.evidence.values()
        if evidence.evidence_type == "document" and evidence.is_copy_of
    )
    return world, world.evidence[copied.is_copy_of], copied


def _full_text(evidence):
    return "\n".join(
        passage["text"]
        for passage in evidence.content_data["written_content"]["passages"]
    )


def test_reading_copy_first_materializes_hidden_root_without_discovering_it():
    world, original, copied = _copy_case()
    knowledge = PlayerKnowledge()
    knowledge.discover_evidence(copied.id)

    assert "written_content" not in original.content_data
    assert "written_content" not in copied.content_data

    materialize_text_carrier(world, copied.id)

    assert original.content_data["text_plan"]["materialization_status"] == "ready"
    assert copied.content_data["text_plan"]["materialization_status"] == "ready"
    assert original.id not in knowledge.discovered_evidence_ids
    assert copied.id in knowledge.discovered_evidence_ids


def test_copy_sections_point_back_to_the_root_and_preserve_most_words():
    world, original, copied = _copy_case(43)
    materialize_text_carrier(world, copied.id)

    source_passages = original.content_data["written_content"]["passages"]
    copied_passages = copied.content_data["written_content"]["passages"]
    for source, derived in zip(source_passages, copied_passages):
        assert derived["source_section_id"] == source["source_section_id"]

    source_text = _full_text(original)
    matcher = SequenceMatcher(None, source_text, _full_text(copied))
    retained_ratio = sum(block.size for block in matcher.get_matching_blocks()) \
        / len(source_text)
    assert retained_ratio >= 0.88
    assert copied.content_data["transmission_variants"]


def test_materialization_and_rereading_are_deterministic_under_concurrency():
    world, original, copied = _copy_case(44)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(
            lambda _: materialize_text_carrier(world, copied.id), range(8)))

    assert len({_full_text(item) for item in results}) == 1
    assert original.content_data["text_plan"]["materialization_status"] == "ready"
    first = read_document(copied, {"common"})
    second = read_document(copied, {"common"})
    assert first == second


def test_damage_is_stable_and_grows_monotonically_after_generation():
    world, original, _ = _copy_case(45)
    materialize_text_carrier(world, original.id)

    original.current_durability = original.max_durability * 0.90
    advance_text_damage(original)
    assert original.content_data["damage_state"]["lesions"] == []

    original.current_durability = original.max_durability * 0.60
    advance_text_damage(original)
    first_lesions = [
        dict(item) for item in original.content_data["damage_state"]["lesions"]
    ]
    first_visible, first_readability = render_damaged_passages(original)
    assert first_lesions

    assert render_damaged_passages(original) == (
        first_visible, first_readability)

    original.current_durability = original.max_durability * 0.25
    advance_text_damage(original)
    later_lesions = original.content_data["damage_state"]["lesions"]
    _, later_readability = render_damaged_passages(original)
    assert later_lesions[:len(first_lesions)] == first_lesions
    assert later_readability < first_readability


def test_materialized_text_layout_and_damage_survive_world_roundtrip():
    world, original, copied = _copy_case(46)
    materialize_text_carrier(world, copied.id)
    copied.current_durability = copied.max_durability * 0.40
    advance_text_damage(copied)
    expected_original = original.content_data.copy()
    expected_copy = copied.content_data.copy()

    restored = World.from_dict(world.to_dict())

    assert restored.evidence[original.id].content_data == expected_original
    assert restored.evidence[copied.id].content_data == expected_copy
    assert render_damaged_passages(restored.evidence[copied.id]) \
        == render_damaged_passages(copied)


def test_legacy_written_content_is_not_rewritten_when_read():
    world, original, _ = _copy_case(47)
    original.content_data["written_content"] = {
        "format_version": 2,
        "language_code": "common",
        "language_name": "通用语",
        "passages": [{"kind": "body", "text": "旧存档原文。"}],
    }
    original.content_data["text_plan"]["materialization_status"] = "ready"
    before = original.content_data["written_content"].copy()

    materialize_text_carrier(world, original.id)
    result = read_document(original, {"common"})

    assert original.content_data["written_content"] == before
    assert "text_layout" not in original.content_data
    assert result["status"] == "readable"
