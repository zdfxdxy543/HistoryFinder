"""Settlement naming guarantees."""

import random

from simulation.names import generate_name, generate_unique_name
from simulation.settlement import SettlementManager


def _create_names(seed: int, count: int) -> list[str]:
    manager = SettlementManager(seed)
    return [
        manager.create_settlement(
            index, index, 0, "plains").name
        for index in range(count)
    ]


def test_large_settlement_batch_has_no_duplicate_names():
    names = _create_names(42, 2000)

    assert len({name.casefold() for name in names}) == len(names)


def test_settlement_name_sequence_is_deterministic():
    assert _create_names(91, 200) == _create_names(91, 200)


def test_collision_retry_does_not_advance_simulation_rng():
    seed = 17
    reference = random.Random(seed + 700)
    first_draw = reference.randint(0, 100000)
    colliding_name = generate_name(first_draw, "settlement")

    manager = SettlementManager(seed)
    manager.used_names.add(colliding_name)
    settlement = manager.create_settlement(0, 0, 0, "plains")

    assert settlement.name.casefold() != colliding_name.casefold()
    assert manager.rng.random() == reference.random()


def test_ruler_names_remain_unique_beyond_base_name_space():
    used_names = set()
    names = [
        generate_unique_name(index, used_names, "ruler")
        for index in range(2000)
    ]

    assert len({name.casefold() for name in names}) == len(names)
