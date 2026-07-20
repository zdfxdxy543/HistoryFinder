"""
Effect 系统的单元测试。
"""

import pytest
from simulation.effects import (
    EffectResolver, EffectResult,
    ModifyPopulation, ModifyFoodStock, ModifyTreasury,
    ModifyStability, ModifyLegitimacy, ModifyRelationship,
    ChangeRuler, DamageBuilding, DestroySettlement, TransferControl,
)


class TestModifyPopulation:
    def test_apply_positive_delta(self):
        """测试正向人口变化。"""
        from simulation.world import World
        w = World(seed=1)
        w.generate(years=0)  # 只初始化，不模拟

        # 手动创建一个简单聚落用于测试
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        effect = ModifyPopulation(settlement_id="test_1", delta=50, reason="test")
        assert effect.validate(w) is True
        result = effect.apply(w)
        assert result.success is True
        assert stl.population == 550

    def test_apply_negative_delta(self):
        from simulation.world import World
        w = World(seed=2)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        effect = ModifyPopulation(settlement_id="test_1", delta=-100, reason="test")
        effect.apply(w)
        assert stl.population == 400

    def test_population_never_below_10(self):
        from simulation.world import World
        w = World(seed=3)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=50)
        w.settlements[stl.id] = stl

        effect = ModifyPopulation(settlement_id="test_1", delta=-500, reason="test")
        effect.apply(w)
        assert stl.population == 10  # 最小值

    def test_validate_fails_on_destroyed_settlement(self):
        from simulation.world import World
        w = World(seed=4)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500, alive=False)
        w.settlements[stl.id] = stl

        effect = ModifyPopulation(settlement_id="test_1", delta=50, reason="test")
        assert effect.validate(w) is False

    def test_percent_change(self):
        from simulation.world import World
        w = World(seed=5)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        effect = ModifyPopulation(settlement_id="test_1", percent=-0.2, reason="test")
        effect.apply(w)
        assert stl.population == 400  # 500 * 0.8


class TestModifyStability:
    def test_clamped_to_0_1_range(self):
        from simulation.world import World
        w = World(seed=6)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=100, stability=0.1)
        w.settlements[stl.id] = stl

        # 降到负值
        effect = ModifyStability(settlement_id="test_1", delta=-0.5, reason="test")
        effect.apply(w)
        assert stl.stability == 0.0

        # 升到超过 1
        effect2 = ModifyStability(settlement_id="test_1", delta=2.0, reason="test")
        effect2.apply(w)
        assert stl.stability == 1.0


class TestEffectResolver:
    def test_transactional_apply(self):
        from simulation.world import World
        w = World(seed=7)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500, stability=0.5)
        w.settlements[stl.id] = stl

        resolver = EffectResolver(seed=100)
        effects = [
            ModifyPopulation(settlement_id="test_1", delta=50, reason="test"),
            ModifyStability(settlement_id="test_1", delta=0.1, reason="test"),
        ]
        ids = resolver.apply_effects(effects, w)
        assert len(ids) == 2
        assert stl.population == 550
        assert stl.stability == 0.6

    def test_rollback_on_invalid_effect(self):
        from simulation.world import World
        w = World(seed=8)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500, stability=0.5)
        w.settlements[stl.id] = stl

        resolver = EffectResolver(seed=200)
        effects = [
            ModifyPopulation(settlement_id="test_1", delta=50, reason="test"),
            ModifyPopulation(settlement_id="nonexistent", delta=10, reason="bad"),
        ]
        ids = resolver.apply_effects(effects, w)
        assert len(ids) == 0  # 全部回滚
        assert stl.population == 500
        assert resolver.applied_effects == {}

    def test_reverse_effect_restores_state(self):
        from simulation.world import World
        from simulation.settlement import Settlement

        w = World(seed=10)
        w.generate(years=0)
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        resolver = EffectResolver(seed=201)
        ids = resolver.apply_effects([
            ModifyPopulation(settlement_id="test_1", delta=75, reason="test"),
        ], w)
        assert stl.population == 575
        assert resolver.reverse_effect(ids[0], w) is True
        assert stl.population == 500

    def test_relationship_reverse_restores_missing_relationship(self):
        from simulation.world import World

        world = World(seed=12)
        world.generate(years=0)
        a, b = list(world.settlements.values())[:2]
        world.current_year = 12
        resolver = EffectResolver(seed=203)

        ids = resolver.apply_effects([
            ModifyRelationship(a.id, b.id, trust_delta=0.1,
                               trade_volume_delta=25.0, reason="test"),
        ], world)
        assert a.relationships[b.id].last_interaction_year == 12
        assert b.relationships[a.id].last_interaction_year == 12
        assert resolver.reverse_effect(ids[0], world)
        assert b.id not in a.relationships
        assert a.id not in b.relationships


class TestChangeRuler:
    def test_ruler_changes(self):
        from simulation.world import World
        w = World(seed=9)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, ruler_name="OldKing")
        w.settlements[stl.id] = stl

        effect = ChangeRuler(settlement_id="test_1",
                             old_ruler_name="OldKing", new_ruler_name="NewKing",
                             change_type="death", reason="test")
        assert effect.validate(w) is True
        result = effect.apply(w)
        assert result.success is True
        assert stl.ruler_name == "NewKing"


def test_destroy_settlement_effect_can_be_reversed():
    from simulation.world import World

    world = World(seed=11)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    evidence_before = {
        evidence.id: evidence.state
        for evidence in world.evidence.values()
        if evidence.location_id == settlement.id
    }

    resolver = EffectResolver(seed=202)
    ids = resolver.apply_effects([
        DestroySettlement(settlement.id, cause="earthquake", reason="test"),
    ], world)
    assert not settlement.alive
    assert resolver.reverse_effect(ids[0], world)
    assert settlement.alive
    assert settlement.destroyed_year is None
    assert {
        evidence.id: evidence.state
        for evidence in world.evidence.values()
        if evidence.location_id == settlement.id
    } == evidence_before
