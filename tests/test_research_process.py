"""Technology-specific research histories and their written records."""

from simulation.event_rules import EventRuleRegistry, EventRuleResult
from simulation.events import HistoricalEvent
from simulation.research import (
    RESEARCH_CATALOG,
    generate_research_process,
)
from simulation.technology import TECHNOLOGY_CATALOG
from simulation.world import World
from simulation.written_content import build_written_content


def _technology(key: str):
    return next(item for item in TECHNOLOGY_CATALOG if item.key == key)


def test_research_catalog_covers_every_technology():
    assert set(RESEARCH_CATALOG) == {
        technology.key for technology in TECHNOLOGY_CATALOG
    }


def test_research_process_is_deterministic_and_ends_in_success():
    technology = _technology("compound_pulley")
    args = (
        42, "event_research", technology, 12,
        "stl_1", "Bridgeheim", "person_1", "Caewyn",
    )

    first = generate_research_process(*args)
    second = generate_research_process(*args)

    assert first == second
    assert first["attempt_count"] == len(first["attempts"])
    assert first["attempts"][-1]["result"] == "repeatable_success"
    assert first["attempts"][-1]["year"] == 12
    assert all(
        attempt["result"] != "repeatable_success"
        for attempt in first["attempts"][:-1]
    )


def test_early_research_keeps_all_attempts_within_world_timeline():
    technology = _technology("chain_pump")
    process = next(
        item for index in range(100)
        if (item := generate_research_process(
            42, f"event_early_{index}", technology, 1,
            "stl_1", "Bridgeheim", "person_1", "Caewyn",
        ))["attempt_count"] >= 4
    )

    years = [attempt["year"] for attempt in process["attempts"]]
    assert years == sorted(years)
    assert min(years) >= 0
    assert years[-1] == 1
    assert process["attempts"][-1]["stage"] == "复现检查"


def test_research_attempt_count_varies_including_direct_success():
    technology = _technology("compound_pulley")
    counts = {
        generate_research_process(
            42, f"event_{index}", technology, 12,
            "stl_1", "Bridgeheim", "person_1", "Caewyn",
        )["attempt_count"]
        for index in range(64)
    }

    assert 1 in counts
    assert len(counts) >= 3


def test_attempt_details_come_from_the_matching_technology_profile():
    technology = _technology("distillation_coil")
    profile = RESEARCH_CATALOG[technology.key]
    processes = [
        generate_research_process(
            19, f"event_distillation_{index}", technology, 20,
            "stl_2", "Rivergate", "person_2", "Ithdred",
        )
        for index in range(20)
    ]

    assert all(process["materials"] == list(profile.materials)
               for process in processes)
    modes = {mode.id: mode for mode in profile.failure_modes}
    for process in processes:
        for attempt in process["attempts"][:-1]:
            mode = modes[attempt["failure_id"]]
            assert attempt["change_for_next_attempt"] in mode.fixes
            assert attempt["observation"] in {
                mode.description, *profile.partial_successes,
            }
        assert process["attempts"][-1]["observation"] \
            in profile.success_indicators


def test_discovery_event_freezes_process_and_roundtrips_in_save_data():
    world = World(seed=501)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    rule = EventRuleRegistry().rules["discovery"]
    outcome = rule.possible_outcomes[0]
    result = EventRuleResult(
        rule=rule,
        settlement=settlement,
        total_score=1.0,
        trigger_factors={},
        selected_outcome=outcome,
        concrete_effects=[],
    )
    event = HistoricalEvent(
        id="event_discovery_process", year=15,
        event_type="discovery", title="discovery",
        severity=0.3, primary_location=settlement.id,
        participants=[settlement.id],
    )

    world._attach_people_to_rule_event(event, result, settlement, 15, {})
    world._add_event(event)
    process = event.details["research_process"]

    assert process["technology_key"] == event.details["technology_key"]
    assert process["completed_year"] == 15
    assert process["lead_researcher_id"] == event.details["discoverer_id"]

    restored = World.from_dict(world.to_dict())
    assert restored.get_event(event.id).details["research_process"] == process


def test_research_notes_render_the_frozen_attempts_not_three_fixed_trials():
    technology = _technology("compound_pulley")
    direct_process = next(
        process for index in range(100)
        if (process := generate_research_process(
            77, f"event_direct_{index}", technology, 9,
            "stl_3", "Fieldmere", "person_3", "Eda",
        ))["attempt_count"] == 1
    )
    event = HistoricalEvent(
        id="event_direct_success", year=9, event_type="discovery",
        title="Fieldmere制成定距排种器", severity=0.3,
        primary_location="stl_3",
        details={
            "discovery_name": technology.title,
            "description_cn": "第9年，定距排种器形成可重复样品。",
            "research_process": direct_process,
        },
    )

    written = build_written_content(
        event, "research_notes", 77, "evd_direct_success")
    text = "\n".join(item["text"] for item in written["passages"])

    assert "共记录1次试制" in text
    assert "第1次试制" in text
    assert "第一次试制失败" not in text
    assert "第二次试制" not in text
    assert "第三次试制" not in text
    assert direct_process["attempts"][0]["observation"] in text


def test_legacy_research_notes_do_not_invent_missing_attempts():
    event = HistoricalEvent(
        id="event_legacy_research", year=9, event_type="discovery",
        title="Legacy discovery", severity=0.3,
        primary_location="stl_3",
        details={
            "discovery_name": "旧式装置",
            "description_cn": "第9年，旧式装置形成可重复样品。",
        },
    )

    written = build_written_content(
        event, "research_notes", 77, "evd_legacy_research")
    text = "\n".join(item["text"] for item in written["passages"])

    assert "试制详页已经散失" in text
    assert "第一次试制" not in text
    assert "第二次试制" not in text
    assert "第三次试制" not in text
