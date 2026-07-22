"""Literature, theory, and their downstream historical effects."""

import copy
import random

import pytest

from narrative.context_builder import build_evidence_context
from narrative.document_reader import read_document
from simulation.effects import (
    EffectResolver,
    ModifyCulturalInfluence,
    ModifyTechnologyLevel,
    ModifyTheoreticalKnowledge,
)
from simulation.event_rules import EventRuleRegistry, EventRuleResult
from simulation.events import HistoricalEvent
from simulation.evidence import Evidence
from simulation.pressures import tick_economy
from simulation.settlement import RelationshipData, Settlement
from simulation.world import World
from simulation.text_carriers import materialize_text_carrier
from simulation.technology import TECHNOLOGY_CATALOG, TECHNOLOGY_BY_SUBTYPE
from simulation.written_content import build_written_content


@pytest.fixture(scope="module")
def developed_world():
    world = World(seed=0)
    world.generate(years=100)
    return world


def test_knowledge_effects_apply_clamp_and_reverse():
    world = World(seed=200)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    resolver = EffectResolver(seed=200)

    effect_ids = resolver.apply_effects([
        ModifyCulturalInfluence(settlement.id, delta=20.0),
        ModifyTheoreticalKnowledge(settlement.id, delta=2.0),
        ModifyTechnologyLevel(settlement.id, delta=1.5),
    ], world)

    assert len(effect_ids) == 3
    assert settlement.cultural_influence == 10.0
    assert settlement.theoretical_knowledge == 2.0
    assert settlement.technology_level == 1.5

    for effect_id in reversed(effect_ids):
        assert resolver.reverse_effect(effect_id, world)
    assert settlement.cultural_influence == 0.0
    assert settlement.theoretical_knowledge == 0.0
    assert settlement.technology_level == 0.0


def test_technology_increases_food_production_with_identical_weather():
    baseline = Settlement(
        id="baseline", name="Baseline", grid_x=0, grid_y=0,
        founded_year=0, population=1000, biome="plains", food_stock=0.0,
    )
    advanced = copy.deepcopy(baseline)
    advanced.id = "advanced"
    advanced.technology_level = 5.0

    tick_economy(baseline, object(), random.Random(99))
    tick_economy(advanced, object(), random.Random(99))

    assert advanced.food_surplus > baseline.food_surplus
    assert advanced.food_shortage < baseline.food_shortage


def test_culture_improves_stability_recovery_with_identical_weather():
    baseline = Settlement(
        id="baseline", name="Baseline", grid_x=0, grid_y=0,
        founded_year=0, population=100, biome="river_valley",
        food_stock=500.0, stability=0.4,
    )
    influenced = copy.deepcopy(baseline)
    influenced.id = "influenced"
    influenced.cultural_influence = 5.0

    tick_economy(baseline, object(), random.Random(101))
    tick_economy(influenced, object(), random.Random(101))

    assert influenced.food_shortage == 0.0
    assert influenced.stability == pytest.approx(baseline.stability + 0.01)


def test_literary_and_theoretical_works_require_a_library():
    world = World(seed=201)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    settlement.population = 500
    settlement.treasury = 500.0
    registry = EventRuleRegistry()

    for event_type in ("literary_work", "theoretical_work"):
        condition = next(
            item for item in registry.rules[event_type].hard_conditions
            if item.name == "has_library"
        )
        settlement.infrastructure.pop("library", None)
        assert not condition.check(world, settlement, 1)
        settlement.infrastructure["library"] = 1.0
        assert condition.check(world, settlement, 1)


def test_new_literary_generation_only_uses_chronicle_and_biography():
    rule = EventRuleRegistry().rules["literary_work"]

    assert {outcome.outcome_type for outcome in rule.possible_outcomes} == {
        "chronicle", "biography",
    }


@pytest.mark.parametrize("genre", ["epic", "drama", "lyric_cycle"])
def test_literary_manuscripts_store_substantial_deterministic_text(genre):
    event = HistoricalEvent(
        id="event_literary", year=12, event_type="literary_work",
        title="A literary work", severity=0.2, primary_location="stl_1",
        details={
            "work_title": "The Returning Road",
            "author_name": "Eda",
            "genre": genre,
        },
    )

    first = build_written_content(event, "literary_manuscript", 42, "evd_1")
    second = build_written_content(event, "literary_manuscript", 42, "evd_1")
    stored_text = "".join(passage["text"] for passage in first["passages"])

    assert first == second
    assert len(first["passages"]) >= 15
    assert len(stored_text) >= 300
    assert all(marker not in stored_text for marker in (
        "本书讲述", "本章讨论", "第一歌讲述", "第一卷追索",
    ))


@pytest.mark.parametrize("genre", ["chronicle", "biography"])
def test_grounded_literature_does_not_append_fixed_explanatory_tail(genre):
    event = HistoricalEvent(
        id=f"event_grounded_{genre}", year=18,
        event_type="literary_work", title="grounded work",
        severity=0.2, primary_location="stl_1",
        details={
            "work_title": "青石镇洪水记录（18年写成）",
            "author_name": "林恩",
            "genre": genre,
            "setting_name": "青石镇",
            "biography_subject_name": "林恩",
            "biography_subject_birth_year": -12,
            "biography_subject_roles": ["ruler"],
            "literary_sources": [{
                "event_id": "event_flood",
                "year": 11,
                "event_type": "disaster",
                "title": "青石镇遭遇春季洪水",
                "summary": "洪水冲坏了南岸粮仓，居民随后重修河堤。",
                "participant_names": ["青石镇"],
                "person_names": ["林恩"],
                "subject_role": "当时的统治者",
            }],
        },
    )

    written = build_written_content(
        event, "literary_manuscript", 42, f"evd_grounded_{genre}")
    text = "\n".join(passage["text"] for passage in written["passages"])

    assert "青石镇遭遇春季洪水" in text
    assert "南岸粮仓" in text
    assert all(marker not in text for marker in (
        "编排说明", "人物说明", "地点说明", "年份说明",
        "来源说明", "增补说明", "综合上述记录", "后续版本",
    ))


@pytest.mark.parametrize("genre,expected_marker", [
    ("epic", "城门"),
    ("drama", "〔第一场"),
    ("chronicle", "编定此书"),
    ("lyric_cycle", "第一首"),
])
def test_literary_manuscripts_contain_the_work_not_a_summary(
        genre, expected_marker):
    event = HistoricalEvent(
        id=f"event_{genre}", year=12, event_type="literary_work",
        title="A literary work", severity=0.2, primary_location="stl_1",
        details={
            "work_title": "The Returning Road",
            "author_name": "Eda",
            "genre": genre,
        },
    )

    written = build_written_content(
        event, "literary_manuscript", 99, f"evd_{genre}")
    stored_text = "".join(
        passage["text"] for passage in written["passages"])

    assert expected_marker in stored_text
    assert "第一歌讲述" not in stored_text
    assert "第一卷追索" not in stored_text


@pytest.mark.parametrize("genre", [
    "epic", "drama", "chronicle", "lyric_cycle",
])
def test_literary_body_uses_frozen_historical_sources(genre):
    event = HistoricalEvent(
        id=f"event_sourced_{genre}", year=18,
        event_type="literary_work", title="A sourced literary work",
        severity=0.2, primary_location="stl_1",
        details={
            "work_title": "The River Remembers",
            "author_name": "Eda",
            "genre": genre,
            "setting_name": "青石镇",
            "literary_sources": [{
                "event_id": "event_flood",
                "year": 11,
                "event_type": "disaster",
                "title": "青石镇遭遇春季洪水",
                "summary": "洪水冲坏了南岸粮仓，居民随后重修河堤。",
                "participant_names": ["青石镇"],
                "person_names": ["林恩"],
            }],
        },
    )

    written = build_written_content(
        event, "literary_manuscript", 42, f"evd_sourced_{genre}")
    stored_text = "\n".join(
        passage["text"] for passage in written["passages"])

    assert "11年" in stored_text
    assert "青石镇遭遇春季洪水" in stored_text
    assert "南岸粮仓" in stored_text
    assert all(marker not in stored_text for marker in (
        "今仅见", "此条未作裁定", "三说并存", "此处留白",
    ))


def test_literary_commentary_is_labeled_and_uses_historical_sources():
    event = HistoricalEvent(
        id="event_commentary", year=52,
        event_type="literary_work", title="A literary commentary",
        severity=0.2, primary_location="stl_1",
        details={
            "work_title": "八任执政者记",
            "author_name": "Caewyn",
            "genre": "chronicle",
            "setting_name": "Bridgeheim",
            "literary_sources": [{
                "event_id": "event_war",
                "year": 32,
                "event_type": "war",
                "title": "Bridgeheim攻陷Markhold",
                "summary": "Bridgeheim的军队攻陷了Markhold。",
                "participant_names": ["Bridgeheim", "Markhold"],
                "person_names": ["Kaelrion", "Nyllin"],
            }],
        },
    )
    written = build_written_content(
        event, "literary_commentary", 42, "evd_commentary")
    evidence = Evidence(
        id="evd_commentary", event_id=event.id,
        evidence_type="document", subtype="literary_commentary",
        location_type="settlement", location_id="stl_1",
        created_year=52, material="parchment",
        max_durability=80, current_durability=80,
        content_data={"written_content": written},
        physical_features={
            "tags": ["legibility:clear_large_letters"],
        },
    )

    reading = read_document(evidence, {"common"})

    assert "作品校注（现存部分）" in reading["text"]
    assert "校者据现存抄本与本地档案" in reading["text"]
    assert "不是作品正文" not in reading["text"]
    assert "Bridgeheim攻陷Markhold" in reading["text"]
    assert "可辨文字" not in reading["text"]


def test_new_literary_work_freezes_only_earlier_local_history():
    world = World(seed=207)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    local_source = HistoricalEvent(
        id="event_local_war", year=6, event_type="war",
        title=f"{settlement.name}守住北门",
        severity=0.8, primary_location=settlement.id,
        participants=[settlement.id],
        details={
            "description_cn": (
                f"6年，{settlement.name}的居民在北门击退了进攻者。"
            ),
        },
        importance_score=0.8,
        visibility_score=0.9,
    )
    future_source = HistoricalEvent(
        id="event_future_flood", year=20, event_type="disaster",
        title=f"{settlement.name}未来的洪水",
        severity=0.9, primary_location=settlement.id,
        participants=[settlement.id],
        details={"description_cn": "这件事在作品创作时尚未发生。"},
        importance_score=0.9,
        visibility_score=0.9,
    )
    world._add_event(local_source)
    world._add_event(future_source)

    rule = EventRuleRegistry().rules["literary_work"]
    outcome = next(
        item for item in rule.possible_outcomes
        if item.outcome_type == "chronicle"
    )
    result = EventRuleResult(
        rule=rule,
        settlement=settlement,
        total_score=1.0,
        trigger_factors={},
        selected_outcome=outcome,
        concrete_effects=[],
    )
    literary_event = HistoricalEvent(
        id="event_new_work", year=12, event_type="literary_work",
        title="new work", severity=0.2,
        primary_location=settlement.id,
        participants=[settlement.id],
    )

    world._attach_people_to_rule_event(
        literary_event, result, settlement, 12, {})

    source_ids = literary_event.details["source_event_ids"]
    assert "event_local_war" in source_ids
    assert "event_future_flood" not in source_ids
    written = build_written_content(
        literary_event, "literary_manuscript", 207,
        "evd_new_sourced_work")
    stored_text = "\n".join(
        passage["text"] for passage in written["passages"])
    assert "6年" in stored_text
    assert f"{settlement.name}守住北门" in stored_text
    assert "未来的洪水" not in stored_text
    assert settlement.name in literary_event.details["work_title"]
    assert "战乱" in literary_event.details["work_title"]


def test_biography_freezes_only_the_subjects_real_earlier_events():
    world = World(seed=208)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    rule = EventRuleRegistry().rules["literary_work"]
    outcome = next(
        item for item in rule.possible_outcomes
        if item.outcome_type == "biography"
    )
    result = EventRuleResult(
        rule=rule,
        settlement=settlement,
        total_score=1.0,
        trigger_factors={},
        selected_outcome=outcome,
        concrete_effects=[],
    )
    literary_event = HistoricalEvent(
        id="event_biography", year=12, event_type="literary_work",
        title="new biography", severity=0.2,
        primary_location=settlement.id, participants=[settlement.id],
    )

    world._attach_people_to_rule_event(
        literary_event, result, settlement, 12, {})

    subject_id = literary_event.details["biography_subject_id"]
    source_ids = literary_event.details["source_event_ids"]
    assert source_ids
    assert literary_event.details["genre"] == "biography"
    assert literary_event.details["biography_subject_name"] in \
        literary_event.details["work_title"]
    for source_id in source_ids:
        source = world.get_event(source_id)
        assert source.year < literary_event.year
        assert subject_id in source.person_ids

    written = build_written_content(
        literary_event, "literary_manuscript", 208,
        "evd_grounded_biography")
    text = "\n".join(passage["text"] for passage in written["passages"])
    assert literary_event.details["biography_subject_name"] in text
    assert all(world.get_event(source_id).title in text
               for source_id in source_ids)


def test_epitaph_uses_the_dead_rulers_frozen_history(developed_world):
    succession = next(
        event for event in developed_world.events
        if event.event_type == "ruler_change"
        and event.details.get("epitaph_sources")
    )
    subject_id = succession.details["epitaph_subject_id"]
    sources = succession.details["epitaph_sources"]
    for source in sources:
        historical_event = developed_world.get_event(source["event_id"])
        assert historical_event.year < succession.year
        assert subject_id in historical_event.person_ids

    tomb = next(
        evidence for evidence in developed_world.evidence.values()
        if evidence.event_id == succession.id
        and evidence.subtype == "ruler_tomb"
    )
    text = "\n".join(
        passage["text"]
        for passage in tomb.content_data["written_content"]["passages"]
    )
    assert succession.details["epitaph_subject_name"] in text
    assert all(source["summary"] in text for source in sources)
    assert all(marker not in text for marker in (
        "人物名册曾记录的身份包括", "当时的摘要为", "此句只记录",
        "共引用", "未记录的行动不列为功绩", "不等同于墓主本人的陈述",
        "founder", "ruler", "general", "scholar", "writer", "heir",
    ))
    assert all(invented not in text for invented in (
        "守过三次歉收之仓", "重开东井", "接纳北来的流民", "整修旧路",
    ))


def test_literary_reader_labels_and_formats_the_work_as_body_text():
    event = HistoricalEvent(
        id="event_readable_literature", year=12,
        event_type="literary_work", title="A literary work",
        severity=0.2, primary_location="stl_1",
        details={
            "work_title": "The Returning Road",
            "author_name": "Eda",
            "genre": "drama",
        },
    )
    written = build_written_content(
        event, "literary_manuscript", 42, "evd_readable_literature")
    evidence = Evidence(
        id="evd_readable_literature", event_id=event.id,
        evidence_type="document", subtype="literary_manuscript",
        location_type="settlement", location_id="stl_1",
        created_year=12, material="parchment",
        max_durability=80, current_durability=80,
        content_data={"written_content": written},
        physical_features={
            "tags": ["legibility:clear_large_letters"],
        },
    )

    reading = read_document(evidence, {"common"})

    assert "作品正文（现存部分）" in reading["text"]
    assert "〔第一场" in reading["text"]
    assert "可辨文字" not in reading["text"]
    assert "  “" not in reading["text"]


def test_technology_catalog_and_generated_artifacts_are_concrete(
        developed_world):
    assert len(TECHNOLOGY_CATALOG) >= 16
    assert len({item.artifact_subtype for item in TECHNOLOGY_CATALOG}) \
        == len(TECHNOLOGY_CATALOG)
    assert len({item.display_name for item in TECHNOLOGY_CATALOG}) \
        == len(TECHNOLOGY_CATALOG)

    discoveries = [
        event for event in developed_world.events
        if event.event_type == "discovery"
    ]
    assert discoveries
    for event in discoveries:
        artifact = next(
            evidence for evidence in developed_world.evidence.values()
            if evidence.event_id == event.id
            and evidence.evidence_type == "artifact"
        )
        profile = TECHNOLOGY_BY_SUBTYPE[artifact.subtype]
        assert artifact.subtype == event.details["artifact_subtype"]
        assert artifact.material == profile.material
        assert artifact.physical_features["display_name"] \
            == profile.display_name
        assert f"form:{profile.form_code}" in \
            artifact.physical_features["tags"]
        assert f"mechanism:{profile.mechanism_code}" in \
            artifact.physical_features["tags"]


def test_theoretical_treatise_stores_method_limits_and_applications():
    event = HistoricalEvent(
        id="event_theory", year=20, event_type="theoretical_work",
        title="A theoretical work", severity=0.2, primary_location="stl_1",
        details={
            "work_title": "On Levers and Loads",
            "author_name": "Oren",
            "theory_field": "mechanics",
        },
    )

    written = build_written_content(
        event, "theoretical_treatise", 42, "evd_2")
    stored_text = "".join(passage["text"] for passage in written["passages"])

    assert len(written["passages"]) >= 17
    assert all(keyword in stored_text for keyword in (
        "试验布置", "反例", "适用限制", "可能用途", "复核办法",
    ))
    assert "尚需由工匠另行试制" in stored_text


def test_literary_spread_preserves_provenance_and_changes_target_culture():
    world = World(seed=202)
    world.generate(years=0)
    source, target = list(world.settlements.values())[:2]
    source.relationships[target.id] = RelationshipData(
        partner_id=target.id, trust=0.6, trade_volume=0.0)
    target.relationships[source.id] = RelationshipData(
        partner_id=source.id, trust=0.6, trade_volume=0.0)
    work = HistoricalEvent(
        id="event_literary_test", year=0, event_type="literary_work",
        title="Aren completes The Returning Road", severity=0.2,
        primary_location=source.id, participants=[source.id],
        process_id="literary_work:event_literary_test",
        details={
            "work_title": "The Returning Road",
            "author_name": "Aren",
            "genre": "epic",
            "genre_name": "长篇叙事诗",
        },
    )
    world.events.append(work)
    world._pending_literary_spreads.append((source.id, 0, work.id))
    culture_before = target.cultural_influence
    trust_before = source.relationships[target.id].trust

    world.current_year = 3
    world._process_literary_spreads(3)
    spread = world.events[-1]

    assert spread.event_type == "literary_spread"
    assert spread.cause_event_ids == [work.id]
    assert spread.process_id == work.process_id
    assert spread.details["genre"] == "epic"
    assert target.cultural_influence > culture_before
    assert source.relationships[target.id].trust > trust_before
    assert world._pending_literary_spreads == []


def test_pending_literary_spreads_roundtrip():
    world = World(seed=203)
    world.generate(years=0)
    source = next(iter(world.settlements.values()))
    world._pending_literary_spreads = [
        (source.id, 7, "event_literary_roundtrip")]

    restored = World.from_dict(world.to_dict())

    assert restored._pending_literary_spreads == [
        (source.id, 7, "event_literary_roundtrip")]


def test_theory_can_be_a_direct_cause_of_later_technology(developed_world):
    events_by_id = {event.id: event for event in developed_world.events}
    linked_discoveries = [
        event for event in developed_world.events
        if event.event_type == "discovery"
        and any(events_by_id[cause_id].event_type == "theoretical_work"
                for cause_id in event.cause_event_ids)
    ]

    assert linked_discoveries
    for discovery in linked_discoveries:
        assert any(
            events_by_id[cause_id].year < discovery.year
            for cause_id in discovery.cause_event_ids
            if events_by_id[cause_id].event_type == "theoretical_work"
        )


def test_new_documents_keep_source_truth_out_of_examination_context(
        developed_world):
    for event_type, subtype in (
            ("literary_work", "literary_manuscript"),
            ("theoretical_work", "theoretical_treatise")):
        evidence = next(
            item for item in developed_world.evidence.values()
            if item.subtype == subtype and item.state != "destroyed"
        )
        source_event = developed_world.get_event(evidence.event_id)
        materialize_text_carrier(developed_world, evidence.id)
        context = build_evidence_context(evidence)
        reading = read_document(evidence, {"common"})

        assert source_event.event_type == event_type
        assert "event_id" not in context
        assert "event_details" not in context
        assert "这件证物与" not in reading["text"]
        assert reading["visible_passages"]
