"""证物描述和玩家信息边界测试。"""

import copy

from game.repl import GameREPL
from narrative.context_builder import build_evidence_context
from narrative.document_reader import (
    is_public_inscription,
    preview_public_inscription,
    read_document,
)
from narrative.evidence_describer import describe_evidence
from narrative.llm_interface import generate_narrative
from simulation.world import World
from simulation.text_carriers import materialize_text_carrier
from simulation.written_content import PUBLIC_INSCRIPTION_SUBTYPES


FORBIDDEN_CONTEXT_KEYS = {
    "event_id", "event_title", "event_year", "event_details",
    "created_year", "participants", "outcome_type",
}


def _first_visible_artifact(world):
    return next(
        evidence for evidence in world.evidence.values()
        if evidence.evidence_type == "artifact"
        and evidence.state in {"intact", "weathered", "ruined"}
    )


def test_physical_feature_tags_are_deterministic():
    first = World(seed=42)
    first.generate(years=20)
    second = World(seed=42)
    second.generate(years=20)

    first_features = {
        evidence_id: evidence.physical_features
        for evidence_id, evidence in first.evidence.items()
    }
    second_features = {
        evidence_id: evidence.physical_features
        for evidence_id, evidence in second.evidence.items()
    }
    assert first_features == second_features

    sample = _first_visible_artifact(first)
    namespaces = {tag.split(":", 1)[0]
                  for tag in sample.physical_features["tags"]}
    assert {"material", "color", "surface", "scale", "mark", "form"} <= namespaces


def test_evidence_context_contains_observations_not_historical_truth():
    world = World(seed=42)
    world.generate(years=20)
    evidence = _first_visible_artifact(world)

    context = build_evidence_context(evidence)
    assert FORBIDDEN_CONTEXT_KEYS.isdisjoint(context)
    assert "physical_features" in context
    assert "observed_name" in context


def test_template_description_does_not_reveal_source_event():
    world = World(seed=42)
    world.generate(years=30)
    evidence = _first_visible_artifact(world)
    event = world.get_event(evidence.event_id)
    context = build_evidence_context(evidence)

    text = generate_narrative(
        "environmental_description", "examine_evidence", context)
    assert event.title not in text
    assert event.details.get("description_cn", "not-present") not in text
    assert "这件证物与" not in text
    assert "不能确定" in text or "无法判断" in text


def test_keyword_composition_changes_with_material_and_type():
    stone_context = {
        "evidence_type": "structure",
        "observed_name": "刻有符号的基石",
        "state_key": "weathered",
        "physical_features": {
            "tags": [
                "material:stone", "color:blue_gray", "surface:fine_chisel_marks",
                "scale:knee_high", "mark:thin_moss", "arrangement:wide_base",
            ],
        },
    }
    metal_context = {
        "evidence_type": "artifact",
        "observed_name": "锈蚀的金属残片",
        "state_key": "intact",
        "physical_features": {
            "tags": [
                "material:metal", "color:rust_red", "surface:pitted_corrosion",
                "scale:one_hand", "mark:remaining_rivet", "form:worn_edges",
            ],
        },
    }

    stone_text = describe_evidence(stone_context)
    metal_text = describe_evidence(metal_context)
    assert "青灰色" in stone_text and "细密凿痕" in stone_text
    assert "红褐色" in metal_text and "点状锈蚀" in metal_text
    assert stone_text != metal_text


def test_oral_traditions_are_not_listed_as_physical_evidence():
    world = World(seed=42)
    world.generate(years=20)
    location_id = next(iter(world.settlements))

    assert any(
        evidence.evidence_type == "oral"
        and evidence.location_id == location_id
        for evidence in world.evidence.values()
    )
    assert all(
        evidence.evidence_type != "oral"
        for evidence in world.get_all_visible_evidence(location_id)
    )


def test_examine_does_not_unlock_internal_event(capsys):
    world = World(seed=42)
    world.generate(years=20)
    location_id = next(
        settlement_id for settlement_id in world.settlements
        if world.get_all_visible_evidence(settlement_id)
    )
    repl = GameREPL(world)
    repl.current_location_id = location_id
    evidence = world.get_all_visible_evidence(location_id)[0]
    source_event = world.get_event(evidence.event_id)

    repl.cmd_examine("1")
    output = capsys.readouterr().out
    assert evidence.id in repl.examined_evidence
    assert repl.known_events == set()
    assert source_event.title not in output

    repl.cmd_events()
    output = capsys.readouterr().out
    assert "还没有足够依据" in output


def test_every_parchment_document_stores_a_lazy_text_plan():
    world = World(seed=42)
    world.generate(years=40)

    parchments = [
        evidence for evidence in world.evidence.values()
        if evidence.material == "parchment"
    ]
    assert parchments
    for evidence in parchments:
        assert evidence.evidence_type == "document"
        assert evidence.content_data.get("text_plan")
        assert "written_content" not in evidence.content_data

        materialize_text_carrier(world, evidence.id)
        written = evidence.content_data["written_content"]
        assert written["language_code"] == "common"
        assert written["passages"]
        assert all(passage.get("text") for passage in written["passages"])


def test_public_inscriptions_store_words_and_expose_only_the_heading_at_glance():
    world = World(seed=42)
    world.generate(years=40)
    inscriptions = [
        evidence for evidence in world.evidence.values()
        if evidence.subtype.removesuffix("_copy")
        in PUBLIC_INSCRIPTION_SUBTYPES
    ]

    assert inscriptions
    assert any(item.evidence_type == "structure" for item in inscriptions)
    for evidence in inscriptions:
        written = evidence.content_data.get("written_content")
        assert written and written["passages"]
        minimum_passages = 5 if evidence.subtype == "ruler_tomb" else 8
        assert len(written["passages"]) >= minimum_passages
        assert all(marker not in "".join(
            passage["text"] for passage in written["passages"])
            for marker in ("碑面刻称", "刻文称", "正面大字刻称"))
        assert is_public_inscription(evidence)
        preview = preview_public_inscription(evidence, {"common"})
        assert preview["status"] == "readable"
        assert preview["text"]
        assert preview["text"] == read_document(
            evidence, {"common"})["visible_passages"][0]


def test_public_inscription_preview_respects_unknown_language():
    world = World(seed=42)
    world.generate(years=0)
    inscription = next(
        evidence for evidence in world.evidence.values()
        if is_public_inscription(evidence))

    preview = preview_public_inscription(inscription, set())

    assert preview["status"] == "unknown_language"
    assert "不能判断这些句子是什么意思" in preview["text"]


def test_document_reading_respects_language_and_is_deterministic():
    world = World(seed=42)
    world.generate(years=20)
    document = next(
        evidence for evidence in world.evidence.values()
        if evidence.material == "parchment" and evidence.state != "destroyed"
    )
    materialize_text_carrier(world, document.id)

    unknown = read_document(document, set())
    assert unknown["status"] == "unknown_language"
    assert "不能判断这些句子是什么意思" in unknown["text"]

    first = read_document(document, {"common"})
    second = read_document(document, {"common"})
    assert first == second
    assert first["status"] == "readable"
    assert first["visible_passages"]
    assert "仍需与其他证据相互核对" not in first["text"]
    assert "这些是文书留下的原话" not in first["text"]


def test_damage_reduces_the_amount_of_readable_text():
    world = World(seed=42)
    world.generate(years=1)
    document = next(
        evidence for evidence in world.evidence.values()
        if evidence.material == "parchment"
    )
    materialize_text_carrier(world, document.id)
    document.physical_features["tags"] = [
        tag for tag in document.physical_features["tags"]
        if not tag.startswith("legibility:")
    ] + ["legibility:isolated_glyphs"]

    intact = copy.deepcopy(document)
    intact.state = "intact"
    intact.current_durability = intact.max_durability
    ruined = copy.deepcopy(document)
    ruined.state = "ruined"
    ruined.current_durability = ruined.max_durability * 0.1

    intact_result = read_document(intact, {"common"})
    ruined_result = read_document(ruined, {"common"})
    assert ruined_result["readability"] < intact_result["readability"]
    assert any("〔" in text for text in ruined_result["visible_passages"])


def test_read_requires_examination_and_does_not_confirm_event(capsys):
    world = World(seed=42)
    world.generate(years=20)
    location_id = next(
        settlement_id for settlement_id in world.settlements
        if any(evidence.evidence_type == "document"
               for evidence in world.get_all_visible_evidence(settlement_id))
    )
    evidence_list = world.get_all_visible_evidence(location_id)
    document_index = next(
        index for index, evidence in enumerate(evidence_list, 1)
        if evidence.evidence_type == "document"
    )
    document = evidence_list[document_index - 1]
    repl = GameREPL(world)
    repl.current_location_id = location_id

    repl.cmd_read(str(document_index))
    output = capsys.readouterr().out
    assert "需要先 examine" in output
    assert document.id not in repl.read_evidence

    repl.cmd_examine(str(document_index))
    capsys.readouterr()
    repl.cmd_read(str(document_index))
    output = capsys.readouterr().out
    assert "可辨文字" in output
    assert "这些是文书留下的原话" not in output
    assert document.id in repl.read_evidence
    assert repl.known_events == set()
