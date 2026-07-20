"""
EventRule 系统的单元测试。
"""

import random
import pytest
from simulation.event_rules import (
    EventRule, EventRuleRegistry, HardCondition, ScoreFactor,
    PossibleOutcome,
)


class TestHardCondition:
    def test_condition_passes(self):
        from simulation.world import World
        w = World(seed=1)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        cond = HardCondition(name="alive", check=lambda w, s, y: s.alive)
        assert cond.check(w, stl, 1) is True

    def test_condition_fails(self):
        from simulation.world import World
        w = World(seed=2)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500, alive=False)
        w.settlements[stl.id] = stl

        cond = HardCondition(name="alive", check=lambda w, s, y: s.alive)
        assert cond.check(w, stl, 1) is False


class TestEventRule:
    def test_evaluate_returns_none_when_hard_condition_fails(self):
        from simulation.world import World
        w = World(seed=3)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=50)  # 人口不足
        w.settlements[stl.id] = stl

        rule = EventRule(
            event_type="test_rebellion",
            hard_conditions=[
                HardCondition(name="min_pop", check=lambda w, s, y: s.population >= 100),
            ],
            base_probability=1.0,
        )
        rng = random.Random(42)
        result = rule.evaluate(w, stl, rng, 1)
        assert result is None

    def test_evaluate_returns_result_when_conditions_met_and_roll_passes(self):
        from simulation.world import World
        w = World(seed=4)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        rule = EventRule(
            event_type="test_rebellion",
            hard_conditions=[
                HardCondition(name="min_pop", check=lambda w, s, y: s.population >= 100),
            ],
            score_factors=[
                ScoreFactor(name="test_factor", weight=0.5,
                           compute=lambda w, s, y: 1.0),  # always max
            ],
            base_probability=0.5,  # + 0.5*1.0 = 1.0 → always passes
        )
        rng = random.Random(42)
        result = rule.evaluate(w, stl, rng, 1)
        assert result is not None
        assert result.total_score >= 0.5
        assert "test_factor" in result.trigger_factors

    def test_evaluate_returns_none_when_roll_fails(self):
        from simulation.world import World
        w = World(seed=5)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        rule = EventRule(
            event_type="test_no_chance",
            hard_conditions=[
                HardCondition(name="min_pop", check=lambda w, s, y: s.population >= 100),
            ],
            base_probability=0.0,
            max_probability=0.0,
        )
        rng = random.Random(42)
        result = rule.evaluate(w, stl, rng, 1)
        assert result is None  # 概率为零

    def test_outcome_selection_is_deterministic(self):
        from simulation.world import World
        w = World(seed=6)
        w.generate(years=0)
        from simulation.settlement import Settlement
        stl = Settlement(id="test_1", name="Test", grid_x=5, grid_y=5,
                         founded_year=0, population=500)
        w.settlements[stl.id] = stl

        rule = EventRule(
            event_type="test",
            hard_conditions=[
                HardCondition(name="alive", check=lambda w, s, y: True),
            ],
            possible_outcomes=[
                PossibleOutcome("A", severity=0.5, base_weight=1.0),
                PossibleOutcome("B", severity=0.8, base_weight=1.0),
            ],
            base_probability=1.0,
        )

        # 两个相同 seed 的 rng，结果一致
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        r1 = rule.evaluate(w, stl, rng1, 1)
        r2 = rule.evaluate(w, stl, rng2, 1)
        assert r1.selected_outcome.outcome_type == r2.selected_outcome.outcome_type


class TestEventRuleRegistry:
    def test_all_rules_registered(self):
        registry = EventRuleRegistry()
        expected_types = ["rebellion", "economic", "disaster", "construction",
                          "trade", "war", "literary_work",
                          "theoretical_work", "discovery"]
        for et in expected_types:
            assert et in registry.rules, f"Missing rule: {et}"

    def test_all_rules_have_outcomes(self):
        registry = EventRuleRegistry()
        for name, rule in registry.rules.items():
            assert len(rule.possible_outcomes) > 0, \
                f"Rule {name} has no outcomes"

    def test_phase1_rules_have_structured_effects(self):
        registry = EventRuleRegistry()
        phase1_types = {"economic", "disaster", "construction", "rebellion", "war"}
        for event_type in phase1_types:
            for outcome in registry.rules[event_type].possible_outcomes:
                assert outcome.effects, \
                    f"{event_type}.{outcome.outcome_type} has no effects"

    def test_all_rules_have_hard_conditions(self):
        registry = EventRuleRegistry()
        for name, rule in registry.rules.items():
            assert len(rule.hard_conditions) > 0, \
                f"Rule {name} has no hard_conditions"

    def test_get_rules_sorted_globals_first(self):
        registry = EventRuleRegistry()
        rules = registry.get_rules_sorted()
        # 第一个应该是 war（唯一 is_global=True）
        assert rules[0].is_global is True
        assert rules[0].event_type == "war"
