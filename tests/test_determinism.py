"""
确定性测试：相同 seed 必须产生相同输出。
"""

import pytest
from simulation.world import World


def test_same_seed_same_world():
    """相同 seed 生成两个 World，验证关键输出一致。"""
    w1 = World(seed=42)
    w1.generate(years=50)
    w2 = World(seed=42)
    w2.generate(years=50)

    # 聚落 ID 和名称一致
    ids1 = sorted(w1.settlements.keys())
    ids2 = sorted(w2.settlements.keys())
    assert ids1 == ids2, f"Settlement IDs differ: {ids1} vs {ids2}"

    # 事件 ID 和年份一致
    events1 = [(e.id, e.year, e.title) for e in w1.events]
    events2 = [(e.id, e.year, e.title) for e in w2.events]
    assert events1 == events2, f"Events differ at index {_first_diff(events1, events2)}"

    # 年末人口一致
    for sid in ids1:
        pop1 = w1.settlements[sid].population
        pop2 = w2.settlements[sid].population
        assert pop1 == pop2, f"Population differs for {sid}: {pop1} vs {pop2}"

    assert {
        person_id: person.to_dict()
        for person_id, person in w1.persons.items()
    } == {
        person_id: person.to_dict()
        for person_id, person in w2.persons.items()
    }


def test_different_seed_different_output():
    """不同 seed 应该产生不同的输出。"""
    w1 = World(seed=42)
    w1.generate(years=30)
    w2 = World(seed=99)
    w2.generate(years=30)

    # 事件标题和详情应该不同（ID 格式相同因为是序列号，但内容因 seed 而异）
    titles1 = [e.title for e in w1.events[:10]]
    titles2 = [e.title for e in w2.events[:10]]
    # 两个不同 seed 的事件标题序列几乎不可能相同
    assert titles1 != titles2, \
        "Different seeds produced identical event titles (extremely unlikely)"


def test_serialization_roundtrip_preserves_state():
    """序列化往返后状态一致。"""
    w1 = World(seed=42)
    w1.generate(years=30)
    data = w1.to_dict()
    w2 = World.from_dict(data)

    # 比较关键字段
    assert w1.seed == w2.seed
    assert w1.current_year == w2.current_year
    assert len(w1.settlements) == len(w2.settlements)
    assert len(w1.events) == len(w2.events)
    assert len(w1.evidence) == len(w2.evidence)
    assert len(w1.persons) == len(w2.persons)

    for e1, e2 in zip(w1.events, w2.events):
        assert e1.id == e2.id
        assert e1.year == e2.year
        assert e1.title == e2.title


def _first_diff(a, b):
    """返回第一个不同元素的索引。"""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    if len(a) != len(b):
        return min(len(a), len(b))
    return -1
