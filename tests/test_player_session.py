"""Playable local-map session tests and truth-boundary checks."""

import pytest

from game.player_session import PlayerActionError, PlayerSession
from simulation.world import World


FORBIDDEN_KEYS = {
    "event_id",
    "source_event_ids",
    "event_ids",
    "event_title",
    "event_details",
    "participants",
    "outcome_type",
    "created_year",
}


@pytest.fixture(scope="module")
def player_session():
    world = World(seed=415)
    world.generate(years=0)
    return PlayerSession(world)


def _all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def test_bootstrap_is_player_safe_and_has_walkable_entities(player_session):
    payload = player_session.bootstrap()
    local_map = payload["local_map"]
    blocking = set(local_map["blocking_tiles"])
    positions = set()

    assert payload["mode"] == "player_safe"
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(payload))
    assert local_map["width"] * local_map["height"] == len(local_map["tiles"])
    assert local_map["entities"]
    for entity in local_map["entities"]:
        position = (entity["x"], entity["y"])
        assert position not in positions
        positions.add(position)
        tile = local_map["tiles"][
            entity["y"] * local_map["width"] + entity["x"]]
        assert tile not in blocking


def test_local_map_contains_living_buildings_and_ordinary_residents(
        player_session):
    local_map = player_session.local_map
    building_types = {
        item["building_type"] for item in local_map["buildings"]}
    residents = [
        item for item in local_map["entities"]
        if item["kind"] == "resident"]
    informant_ids = {
        item["id"] for item in local_map["entities"]
        if item["kind"] == "informant"}

    assert {"home", "inn", "bakery", "granary", "well"} <= building_types
    assert len(residents) >= 6
    assert all(item["role_name"] for item in residents)
    assert all(item["description_cn"] for item in residents)
    assert len({item["dialogue_cn"] for item in residents}) == len(residents)
    assert informant_ids.isdisjoint(item["id"] for item in residents)


def test_talking_to_resident_is_safe_and_does_not_create_claims(player_session):
    resident = next(
        item for item in player_session.local_map["entities"]
        if item["kind"] == "resident")
    claims_before = player_session.journal_payload()["counts"]["claims"]

    result = player_session.talk(resident["id"])

    assert result["action"] == "talk"
    assert result["resident"]["role_name"]
    assert result["dialogue_cn"]
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(result))
    assert player_session.journal_payload()["counts"]["claims"] == claims_before


def test_read_requires_examination(player_session):
    document_id = next(
        item["id"] for item in player_session.local_map["entities"]
        if item["kind"] == "evidence" and item["subtype"] == "document")

    with pytest.raises(PlayerActionError, match="先检查"):
        player_session.read(document_id)


def test_examine_read_and_consult_update_safe_journal(player_session):
    document_id = next(
        item["id"] for item in player_session.local_map["entities"]
        if item["kind"] == "evidence" and item["subtype"] == "document")
    informant_id = next(
        item["id"] for item in player_session.local_map["entities"]
        if item["kind"] == "informant")

    examined = player_session.examine(document_id)
    read = player_session.read(document_id)
    consulted = player_session.consult(document_id, informant_id)

    assert examined["observations"]
    assert read["reading"]["evidence_id"] == document_id
    assert consulted["consultation"]["consultant_id"] == informant_id
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(examined))
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(read))
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(consulted))
    assert player_session.journal_payload()["counts"]["examined"] >= 1


def test_compare_two_examined_map_objects(player_session):
    evidence_ids = [
        item["id"] for item in player_session.local_map["entities"]
        if item["kind"] == "evidence"][:2]
    assert len(evidence_ids) == 2
    for evidence_id in evidence_ids:
        player_session.examine(evidence_id)

    result = player_session.compare(*evidence_ids)

    assert result["comparison"]["evidence_ids"]
    assert result["comparison"]["limitations_cn"]
    assert FORBIDDEN_KEYS.isdisjoint(_all_keys(result))


def test_local_map_is_deterministic():
    first_world = World(seed=416)
    second_world = World(seed=416)
    first_world.generate(years=0)
    second_world.generate(years=0)

    assert PlayerSession(first_world).local_map == PlayerSession(
        second_world).local_map
