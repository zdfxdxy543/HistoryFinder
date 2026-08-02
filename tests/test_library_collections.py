"""Lightweight library holdings, persistence, and player interaction tests."""

import json
from collections import deque

from game.player_session import PlayerSession
from simulation.library import (
    LibraryBook,
    build_library_catalog,
    library_book_count,
    materialize_library_book,
    render_library_book,
)
from simulation.settlement import Settlement
from simulation.world import World


def _settlement(identifier: str, *, size: str, level: float,
                culture: float, theory: float) -> Settlement:
    return Settlement(
        id=identifier,
        name=f"Library {identifier}",
        grid_x=10,
        grid_y=10,
        founded_year=0,
        alive=True,
        size=size,
        population=800,
        infrastructure={"library": level},
        cultural_influence=culture,
        theoretical_knowledge=theory,
    )


def _stand_next_to(session: PlayerSession, entity: dict) -> None:
    local_map = session.local_map
    width, height = local_map["width"], local_map["height"]
    blocking = set(local_map["blocking_tiles"])
    occupied = {
        (item["x"], item["y"])
        for item in local_map["entities"]
        if item.get("blocks_movement", True)
    }
    start = (local_map["player_start"]["x"], local_map["player_start"]["y"])
    queue = deque([start])
    reached = {start}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            point = (x + dx, y + dy)
            if point in reached or not (0 <= point[0] < width and 0 <= point[1] < height):
                continue
            if local_map["tiles"][point[1] * width + point[0]] in blocking:
                continue
            if point in occupied:
                continue
            reached.add(point)
            queue.append(point)
    neighbor = next(
        point for point in sorted(reached)
        if abs(point[0] - entity["x"]) + abs(point[1] - entity["y"]) == 1
    )
    session.local_time.player = {"x": neighbor[0], "y": neighbor[1]}


def test_catalog_size_scales_and_generation_is_deterministic():
    small = _settlement(
        "small", size="village", level=0.5, culture=0.0, theory=0.0)
    large = _settlement(
        "large", size="city", level=2.0, culture=5.0, theory=5.0)

    assert 20 <= library_book_count(small, 30) < library_book_count(large, 30)
    first = build_library_catalog(42, large, "collection_large", 30)
    second = build_library_catalog(42, large, "collection_large", 30)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert len({item.id for item in first}) == len(first)
    assert len({item.title for item in first}) > 20
    assert max(int(item.shelf_id.rsplit("_", 1)[-1]) for item in first) <= 12
    assert not any("text" in item.to_dict() for item in first)
    assert all(item.text_plan["materialization_status"] == "planned" for item in first)
    assert not any(item.written_content for item in first)

    by_genre = {}
    for book in first:
        by_genre.setdefault(book.genre, book)
    texts = {genre: materialize_library_book(book) for genre, book in by_genre.items()}
    assert set(texts) == set(book.genre for book in first)
    assert len(set(texts.values())) == len(texts)
    assert all(3 <= len(book.written_content["sections"]) <= 6 for book in by_genre.values())
    assert all(book.text_plan["materialization_status"] == "ready" for book in by_genre.values())


def test_world_roundtrip_and_schema_19_migration_preserve_or_build_catalogs():
    world = World(seed=42)
    world.generate(years=30)
    assert world.library_books

    data = json.loads(json.dumps(world.to_dict(), ensure_ascii=False))
    restored = World.from_dict(data)
    assert {
        key: item.to_dict() for key, item in restored.library_books.items()
    } == {
        key: item.to_dict() for key, item in world.library_books.items()
    }

    data["schema_version"] = 19
    data.pop("library_books")
    migrated = World.from_dict(data)
    assert migrated.library_books
    assert len(migrated.library_books) == len(world.library_books)


def test_bookshelves_expose_many_books_and_lazy_reading_is_not_evidence():
    world = World(seed=42)
    world.generate(years=30)
    settlement = next(
        item for item in world.settlements.values()
        if world.get_library_books(item.id)
    )
    session = PlayerSession(world, settlement.id)
    shelves = [
        item for item in session.local_map["entities"]
        if item["kind"] == "bookshelf"
    ]

    assert shelves
    assert len(shelves) <= 12
    assert sum(item["book_count"] for item in shelves) == len(
        world.get_library_books(settlement.id))
    shelf = shelves[0]
    _stand_next_to(session, shelf)
    journal_before = session.journal_payload()["counts"].copy()

    catalog = session.browse_bookshelf(shelf["id"])
    assert len(catalog["library_books"]) == shelf["book_count"]
    assert "text_cn" not in catalog
    book = world.library_books[catalog["library_books"][0]["id"]]
    assert not book.written_content

    reading = session.read_library_book(book.id)
    assert reading["action"] == "read_library_book"
    assert book.title in reading["text_cn"]
    assert 3 <= len(reading["library_sections"]) <= 6
    assert all(item["heading"] and item["text"] for item in reading["library_sections"])
    assert book.written_content["generator_version"] == "ordinary-books-v2"
    cached = json.loads(json.dumps(book.written_content, ensure_ascii=False))
    repeated = session.read_library_book(book.id)
    assert repeated["library_sections"] == reading["library_sections"]
    assert repeated["readability_ratio"] == reading["readability_ratio"]
    assert book.written_content == cached
    assert session.journal_payload()["counts"] == journal_before
    assert book.id not in world.evidence

    restored = World.from_dict(json.loads(json.dumps(world.to_dict(), ensure_ascii=False)))
    assert restored.library_books[book.id].written_content == cached
    assert restored.library_books[book.id].damage_state == book.damage_state


def test_book_damage_is_deterministic_monotonic_and_keeps_pristine_text():
    settlement = _settlement(
        "damage", size="city", level=2.0, culture=4.0, theory=4.0)
    source = build_library_catalog(71, settlement, "collection_damage", 180)[0]
    views = {}
    books = {}
    for condition in ("intact", "worn", "fragile"):
        book = LibraryBook.from_dict(source.to_dict())
        book.condition = condition
        book.damage_state = {}
        pristine_text = materialize_library_book(book)
        pristine_sections = json.loads(json.dumps(
            book.written_content["sections"], ensure_ascii=False))
        view = render_library_book(book)

        assert book.written_content["text_cn"] == pristine_text
        assert book.written_content["sections"] == pristine_sections
        assert render_library_book(book) == view
        views[condition] = view
        books[condition] = book

    assert views["intact"]["readability_ratio"] == 1.0
    assert (
        views["intact"]["readability_ratio"]
        > views["worn"]["readability_ratio"]
        > views["fragile"]["readability_ratio"]
    )
    assert 0.05 <= books["worn"].damage_state["loss_ratio"] <= 0.15
    assert 0.20 <= books["fragile"].damage_state["loss_ratio"] <= 0.40
    assert any(
        section["status"] == "missing"
        for section in views["fragile"]["sections"]
    )
    assert any(
        marker in section["text"]
        for section in views["worn"]["sections"]
        for marker in ("〔字迹褪色〕", "〔水渍漫漶〕")
    )

    restored = LibraryBook.from_dict(json.loads(json.dumps(
        books["fragile"].to_dict(), ensure_ascii=False)))
    assert restored.damage_state == books["fragile"].damage_state
    assert render_library_book(restored) == views["fragile"]
