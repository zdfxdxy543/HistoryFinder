from game.local_map import LocalMapBuilder, TILE_BRIDGE, TILE_FENCE, TILE_ROAD
from game.local_time import LocalTimeSimulation
from game.player_session import PlayerSession
from game.world_cell_map import WorldCellMapBuilder, cell_key
from simulation.historical_sites import CEMETERY_PLOT_CAPACITY
from simulation.world import World


def _written_text(evidence) -> str:
    return "\n".join(
        passage["text"]
        for passage in evidence.content_data["written_content"]["passages"]
    )


def _kill_non_rulers(world, settlement_id: str, count: int,
                      death_year: int) -> list:
    people = [
        person for person in world.persons.values()
        if person.settlement_id == settlement_id
        and "ruler" not in person.roles
    ][:count]
    assert len(people) == count
    for person in people:
        person.alive = False
        person.death_year = death_year
    return people


def test_every_rendered_grave_has_a_real_person_and_complete_inscription():
    world = World(seed=601)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    dead = _kill_non_rulers(world, settlement.id, 2, 1)
    world.current_year = 12

    world._sync_historical_sites()

    burials = [
        burial for burial in world.burials.values()
        if burial.person_id in {person.id for person in dead}
    ]
    assert len(burials) == 2
    for burial in burials:
        assert burial.person_id in world.persons
        person = world.persons[burial.person_id]
        marker = world.evidence[burial.inscription_evidence_id]
        text = _written_text(marker)
        assert person.name in text
        birth_label = (f"纪元前{-person.birth_year}年"
                       if person.birth_year < 0
                       else f"{person.birth_year}年")
        assert birth_label in text
        assert str(person.death_year) in text
        assert len(marker.content_data["written_content"]["passages"]) >= 6
        assert marker.content_data["person_id"] == person.id
        for event_id in burial.source_event_ids:
            event = world.get_event(event_id)
            assert event is not None
            assert person.id in event.person_ids
            assert event.year <= person.death_year

    site = world.historical_sites[f"site_cemetery_{settlement.id}"]
    settlement_cell = (int(settlement.grid_x), int(settlement.grid_y))
    if site.anchor_cell == settlement_cell:
        local_map = LocalMapBuilder().build(world, settlement)
    else:
        assert sum(abs(a - b) for a, b in zip(
            site.anchor_cell, settlement_cell)) == 1
        local_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    cemetery = next(
        building for building in local_map["buildings"]
        if building["building_type"] == "cemetery")
    left, top, right, bottom = cemetery["bounds"]
    assert right - left + 1 <= 6
    assert bottom - top + 1 <= 8
    boundary = {
        local_map["tiles"][y * local_map["width"] + x]
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if x in {left, right} or y in {top, bottom}
    }
    assert TILE_FENCE in boundary
    grave_entities = [
        entity for entity in local_map["entities"]
        if entity["id"] in {
            burial.inscription_evidence_id for burial in burials}
    ]
    assert len(grave_entities) == len(burials)
    assert len({(item["x"], item["y"]) for item in grave_entities}) \
        == len(grave_entities)
    assert all(left < item["x"] < right and top < item["y"] < bottom
               for item in grave_entities)

    if site.anchor_cell == settlement_cell:
        cemetery_index = local_map["buildings"].index(cemetery)
        assert all(
            building["building_type"] == "cemetery"
            for building in local_map["buildings"][cemetery_index:])
    else:
        assert all(
            world.evidence[burial.inscription_evidence_id].location_id
            == cell_key(*site.anchor_cell)
            for burial in burials)


def test_old_real_burials_create_a_multitile_wilderness_cemetery():
    world = World(seed=602)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    dead = _kill_non_rulers(world, settlement.id, 3, 2)
    world.current_year = 50

    world._sync_historical_sites()

    site = world.historical_sites[
        f"site_abandoned_cemetery_{settlement.id}"]
    assert site.state == "abandoned"
    assert site.anchor_cell != (
        int(settlement.grid_x), int(settlement.grid_y))
    burials = [
        burial for burial in world.burials.values()
        if burial.person_id in {person.id for person in dead}
    ]
    assert all(burial.site_id == site.id for burial in burials)
    assert all(
        world.evidence[burial.inscription_evidence_id].location_id
        == cell_key(*site.anchor_cell)
        for burial in burials)

    local_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    building = next(
        item for item in local_map["buildings"]
        if item["historical_site_id"] == site.id)
    left, top, right, bottom = building["bounds"]
    assert right - left + 1 <= 6 and bottom - top + 1 <= 8
    road_cells = {
        (x, y)
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
        if local_map["tiles"][y * local_map["width"] + x]
        in {TILE_ROAD, TILE_BRIDGE}
    }
    door = (building["door"]["x"], building["door"]["y"])
    assert all(
        abs(x - door[0]) + abs(y - door[1]) <= 1
        for x, y in road_cells)
    grave_ids = {burial.inscription_evidence_id for burial in burials}
    assert grave_ids <= {
        item["id"] for item in local_map["entities"]
        if item["kind"] == "evidence"}


def test_full_cemetery_opens_a_new_wilderness_plot_without_overlapping_graves():
    world = World(seed=606)
    world.generate(years=0)
    settlement = max(world.settlements.values(), key=lambda item: sum(
        person.settlement_id == item.id and "ruler" not in person.roles
        for person in world.persons.values()))
    dead = _kill_non_rulers(
        world, settlement.id, CEMETERY_PLOT_CAPACITY + 1, 1)
    world.current_year = 12

    world._sync_historical_sites()

    person_ids = {person.id for person in dead}
    burials = [
        burial for burial in world.burials.values()
        if burial.person_id in person_ids]
    plots = [
        site for site in world.historical_sites.values()
        if site.site_type == "cemetery"
        and site.owner_settlement_id == settlement.id
        and any(burial.site_id == site.id for burial in burials)
    ]
    assert len(plots) == 2
    assert all(sum(
        burial.site_id == site.id for burial in burials
    ) <= CEMETERY_PLOT_CAPACITY for site in plots)
    settlement_cell = (int(settlement.grid_x), int(settlement.grid_y))
    assert any(site.anchor_cell != settlement_cell for site in plots)

    for site in plots:
        plot_burials = [
            burial for burial in burials if burial.site_id == site.id]
        local_map = (
            LocalMapBuilder().build(world, settlement)
            if site.anchor_cell == settlement_cell else
            WorldCellMapBuilder().build(world, *site.anchor_cell)
        )
        building = next(
            item for item in local_map["buildings"]
            if item.get("historical_site_id") == site.id
            or (site.anchor_cell == settlement_cell
                and item["building_type"] == "cemetery"))
        left, top, right, bottom = building["bounds"]
        grave_ids = {
            burial.inscription_evidence_id for burial in plot_burials}
        graves = [
            item for item in local_map["entities"]
            if item["id"] in grave_ids]
        assert len(graves) == len(plot_burials)
        assert len({(item["x"], item["y"]) for item in graves}) == len(graves)
        assert all(
            left < item["x"] < right and top < item["y"] < bottom
            for item in graves)


def test_war_creates_cross_cell_ruins_and_moves_nearby_evidence_to_site():
    world = World(seed=603)
    world.generate(years=0)
    attacker, defender = list(world.settlements.values())[:2]
    event = world._event_gen.generate_war_event(
        4, attacker.id, attacker.name, defender.id, defender.name,
        defender.id, "stalemate")
    world._add_event_with_evidence(event)
    world.current_year = 4

    world._sync_historical_sites()

    site = world.historical_sites[f"site_battlefield_ruins_{event.id}"]
    assert len(site.occupied_cells) == 2
    nearby = [
        evidence for evidence in world.get_evidence_by_event(event.id)
        if evidence.location_type == "grid_cell"
    ]
    assert nearby
    assert all(evidence.location_id == cell_key(*site.anchor_cell)
               for evidence in nearby)
    for occupied_cell in site.occupied_cells:
        local_map = WorldCellMapBuilder().build(world, *occupied_cell)
        building = next(
            item for item in local_map["buildings"]
            if item["historical_site_id"] == site.id)
        left, top, right, bottom = building["bounds"]
        assert right > left and bottom > top


def test_trade_route_creates_a_real_multitile_roadside_building():
    world = World(seed=604)
    world.generate(years=0)
    first, second = list(world.settlements.values())[:2]
    route = world.ensure_trade_route(first.id, second.id)
    assert route is not None and len(route.path) > 2

    world._sync_historical_sites()

    route_sites = [
        site for site in world.historical_sites.values()
        if site.route_id == route.id
    ]
    assert len(route_sites) == 1
    site = route_sites[0]
    local_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    building = next(
        item for item in local_map["buildings"]
        if item["historical_site_id"] == site.id)
    left, top, right, bottom = building["bounds"]
    assert right - left >= 14
    assert bottom - top >= 9
    assert not any(
        local_map["tiles"][y * local_map["width"] + x]
        in {TILE_ROAD, TILE_BRIDGE}
        for y in range(top, bottom + 1)
        for x in range(left, right + 1)
    )
    assert not any(
        entity["id"].startswith(f"landmark_{site.id}")
        for entity in local_map["entities"])
    assert set(site.evidence_ids) <= {
        entity["id"] for entity in local_map["entities"]}
    assert local_map["historical_site_signature"]


def test_active_wilderness_site_staff_persist_and_follow_site_state():
    world = World(seed=614)
    world.generate(years=0)
    first, second = list(world.settlements.values())[:2]
    route = world.ensure_trade_route(first.id, second.id)
    assert route is not None and len(route.path) > 2
    world._sync_historical_sites()
    site = next(
        item for item in world.historical_sites.values()
        if item.route_id == route.id)
    staff_ids = [item.id for item in site.staff_members]

    assert staff_ids
    assert all(item.active for item in site.staff_members)
    local_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    building = next(
        item for item in local_map["buildings"]
        if item["historical_site_id"] == site.id)
    staff_entities = [
        item for item in local_map["entities"]
        if item.get("historical_site_id") == site.id
        and item.get("site_staff")
    ]
    assert {item["id"] for item in staff_entities} == set(staff_ids)
    assert all(item["kind"] == "resident" for item in staff_entities)
    left, top, right, bottom = building["bounds"]
    assert all(
        left < item["x"] < right and top < item["y"] < bottom
        for item in staff_entities)

    local_time = LocalTimeSimulation(local_map, settle_npcs=True)
    assert set(staff_ids) <= set(local_time._npcs)
    assert all(
        left < local_time._npcs[item_id]["x"] < right
        and top < local_time._npcs[item_id]["y"] < bottom
        for item_id in staff_ids)
    session = PlayerSession(world, first.id)
    session.current_cell = site.anchor_cell
    session.current_location_id = None
    session.local_map = local_map
    session.local_time = local_time
    conversation = session.talk(staff_ids[0])
    assert conversation["action"] == "talk"
    assert conversation["dialogue_cn"]

    site.state = "damaged"
    site.revision += 1
    damaged_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    damaged_staff = [
        item for item in damaged_map["entities"] if item.get("site_staff")]
    assert len(damaged_staff) == max(1, (len(staff_ids) + 1) // 2)

    route.status = "abandoned"
    route.closed_year = world.current_year
    world._sync_historical_sites()
    assert not any(item.active for item in site.staff_members)
    abandoned_map = WorldCellMapBuilder().build(world, *site.anchor_cell)
    assert not any(item.get("site_staff") for item in abandoned_map["entities"])

    route.status = "active"
    route.closed_year = None
    world._sync_historical_sites()
    assert [item.id for item in site.staff_members] == staff_ids
    assert all(item.active for item in site.staff_members)


def test_old_historical_site_schema_generates_staff_on_load():
    world = World(seed=615)
    world.generate(years=0)
    data = world.to_dict()
    for site in data["historical_sites"]:
        site["schema_version"] = 1
        site.pop("staff_members", None)

    restored = World.from_dict(data)
    staffed = [
        site for site in restored.historical_sites.values()
        if site.site_type in {
            "roadside_inn", "tollhouse", "farmstead", "mine",
            "logging_camp", "watchtower", "cemetery"}
        and site.state in {"active", "damaged", "restored"}
    ]
    assert staffed
    assert all(site.schema_version == 2 for site in staffed)
    assert all(site.staff_members for site in staffed)


def test_historical_sites_and_burials_survive_world_roundtrip():
    world = World(seed=605)
    world.generate(years=0)
    settlement = next(iter(world.settlements.values()))
    _kill_non_rulers(world, settlement.id, 1, 1)
    world.current_year = 8
    world._sync_historical_sites()

    restored = World.from_dict(world.to_dict())

    assert {
        key: site.to_dict() for key, site in restored.historical_sites.items()
    } == {
        key: site.to_dict() for key, site in world.historical_sites.items()
    }
    assert {
        key: burial.to_dict() for key, burial in restored.burials.items()
    } == {
        key: burial.to_dict() for key, burial in world.burials.items()
    }
