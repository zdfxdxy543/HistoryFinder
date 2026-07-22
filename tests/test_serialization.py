"""
序列化测试：验证所有核心 dataclass 的 to_dict/from_dict。
"""

from simulation.world import World
from simulation.settlement import Settlement, RelationshipData
from simulation.events import HistoricalEvent
from simulation.evidence import Evidence
from simulation.person import Person


def test_settlement_roundtrip():
    """Settlement 序列化往返。"""
    s1 = Settlement(
        id="stl_0001", name="Testville",
        grid_x=10, grid_y=20, founded_year=0,
        population=500, peak_population=600,
        biome="river_valley", size="town",
        ruler_name="Thaldor", ruler_id="person_0001",
        food_stock=800.0, treasury=300.0,
        stability=0.8, legitimacy=0.85,
        cultural_influence=1.25,
        theoretical_knowledge=2.5,
        technology_level=0.75,
        food_shortage=0.2,
        infrastructure={"market": 2.0},
    )
    data = s1.to_dict()
    s2 = Settlement.from_dict(data)

    assert s2.id == s1.id
    assert s2.name == s1.name
    assert s2.population == 500
    assert s2.food_stock == 800.0
    assert s2.stability == 0.8
    assert s2.legitimacy == 0.85
    assert s2.cultural_influence == 1.25
    assert s2.theoretical_knowledge == 2.5
    assert s2.technology_level == 0.75
    assert s2.ruler_name == "Thaldor"
    assert s2.ruler_id == "person_0001"
    assert s2.food_shortage == 0.2
    assert s2.infrastructure == {"market": 2.0}


def test_relationship_data_roundtrip():
    """RelationshipData 序列化往返。"""
    r1 = RelationshipData(
        partner_id="stl_0002",
        trust=0.8, hostility=0.1,
        trade_volume=50.0,
        last_interaction_year=25,
        treaty_ids=["tr_001", "tr_002"],
        exchange_counts={"trade": 4, "scholarly": 2},
        exchange_strengths={"trade": 1.12, "scholarly": 0.68},
        exchange_last_years={"trade": 25, "scholarly": 24},
        exchange_topics={
            "trade": ["compound_pulley"],
            "scholarly": ["mechanics"],
        },
    )
    data = r1.to_dict()
    r2 = RelationshipData.from_dict(data)

    assert r2.partner_id == r1.partner_id
    assert r2.trust == 0.8
    assert r2.trade_volume == 50.0
    assert r2.treaty_ids == ["tr_001", "tr_002"]
    assert r2.exchange_counts == {"trade": 4, "scholarly": 2}
    assert r2.exchange_strengths == {"trade": 1.12, "scholarly": 0.68}
    assert r2.exchange_last_years == {"trade": 25, "scholarly": 24}
    assert r2.exchange_topics["trade"] == ["compound_pulley"]


def test_legacy_relationship_defaults_to_empty_exchange_networks():
    legacy = RelationshipData(
        partner_id="stl_0002", trust=0.6).to_dict()
    for key in (
        "exchange_counts", "exchange_strengths",
        "exchange_last_years", "exchange_topics",
    ):
        legacy.pop(key)

    restored = RelationshipData.from_dict(legacy)

    assert restored.exchange_counts == {}
    assert restored.exchange_strengths == {}
    assert restored.exchange_last_years == {}
    assert restored.exchange_topics == {}


def test_event_roundtrip():
    """HistoricalEvent 序列化往返含新字段。"""
    e1 = HistoricalEvent(
        id="event_0001", year=10, event_type="rebellion",
        title="Testville 叛乱", severity=0.6,
        primary_location="stl_0001",
        participants=["stl_0001"],
        person_ids=["person_0001"],
        cause_event_ids=["event_0000"],
        effect_ids=["effect_000001"],
        effects=[{"effect_type": "modify_stability", "delta": -0.1}],
        trigger_factors={"unrest_pressure": 0.72, "famine_contribution": 0.45},
        importance_score=0.7,
        visibility_score=0.8,
    )
    data = e1.to_dict()
    e2 = HistoricalEvent.from_dict(data)

    assert e2.id == e1.id
    assert e2.year == 10
    assert e2.trigger_factors == {"unrest_pressure": 0.72, "famine_contribution": 0.45}
    assert e2.cause_event_ids == ["event_0000"]
    assert e2.importance_score == 0.7
    assert e2.effect_ids == ["effect_000001"]
    assert e2.effects == [{"effect_type": "modify_stability", "delta": -0.1}]
    assert e2.person_ids == ["person_0001"]


def test_person_roundtrip():
    person = Person(
        id="person_0001", name="Thaldor", birth_year=-35,
        settlement_id="stl_0001", roles=["founder", "ruler"],
        parent_ids=["person_0000"], spouse_ids=["person_0002"],
    )
    restored = Person.from_dict(person.to_dict())
    assert restored == person


def test_evidence_roundtrip():
    """Evidence 序列化往返。"""
    evd1 = Evidence(
        id="evd_0001", event_id="event_0001",
        evidence_type="document", subtype="rebel_manifesto",
        location_type="settlement", location_id="stl_0001",
        created_year=10, material="parchment",
        max_durability=80.0, current_durability=60.0,
        state="weathered", discoverability=0.3,
        content_data={"event_title": "Testville 叛乱"},
        narrative_bias="official",
        physical_features={
            "display_name": "字迹密集的文书残片",
            "tags": ["material:parchment", "color:dark_yellow"],
        },
    )
    data = evd1.to_dict()
    evd2 = Evidence.from_dict(data)

    assert evd2.id == evd1.id
    assert evd2.material == "parchment"
    assert evd2.state == "weathered"
    assert evd2.current_durability == 60.0
    assert evd2.narrative_bias == "official"
    assert evd2.physical_features == evd1.physical_features
    assert evd2.content_data == evd1.content_data


def test_world_roundtrip():
    """World 序列化往返（不含地理图层）。"""
    w1 = World(seed=42)
    w1.generate(years=30)
    data = w1.to_dict()
    w2 = World.from_dict(data)

    assert w2.seed == 42
    assert w2.current_year == 30
    assert len(w2.settlements) == len(w1.settlements)
    assert len(w2.events) == len(w1.events)
    assert len(w2.evidence) == len(w1.evidence)
    assert len(w2.persons) == len(w1.persons)
    assert w2._pending_disaster_aftermaths == w1._pending_disaster_aftermaths
    assert w2._pending_literary_spreads == w1._pending_literary_spreads

    # 验证每个 settlement
    for s1 in w1.settlements.values():
        s2 = w2.settlements.get(s1.id)
        assert s2 is not None
        assert s2.name == s1.name
        assert s2.population == s1.population
        assert s2.alive == s1.alive
        assert s2.ruler_id == s1.ruler_id

    for person_id, person in w1.persons.items():
        assert w2.persons[person_id].to_dict() == person.to_dict()


def test_old_world_save_migrates_missing_document_text_to_a_lazy_plan():
    world = World(seed=42)
    world.generate(years=1)
    data = world.to_dict()
    document_data = next(
        evidence for evidence in data["evidence"]
        if evidence["evidence_type"] == "document"
    )
    document_data["content_data"].pop("written_content", None)
    document_data["content_data"].pop("text_plan", None)
    document_data["schema_version"] = 3

    restored = World.from_dict(data)
    document = restored.evidence[document_data["id"]]
    assert document.schema_version == 7
    assert "written_content" not in document.content_data
    assert document.content_data["text_plan"]["materialization_status"] \
        == "planned"


def test_old_world_save_rebuilds_legacy_rulers():
    world = World(seed=42)
    world.generate(years=1)
    data = world.to_dict()
    data.pop("persons")
    for settlement in data["settlements"]:
        settlement.pop("ruler_id")

    restored = World.from_dict(data)
    for settlement in restored.settlements.values():
        ruler = restored.get_person(settlement.ruler_id)
        assert ruler is not None
        assert ruler.name == settlement.ruler_name
