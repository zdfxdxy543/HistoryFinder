"""Persistent historical sites and person-bound burials."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


SITE_STATES = {"active", "damaged", "abandoned", "ruined", "restored"}
CEMETERY_PLOT_CAPACITY = 6


def _stable_int(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(
        "|".join(parts).encode("utf-8")).digest()[:8], "big")


@dataclass
class HistoricalSite:
    id: str
    name: str
    site_type: str
    anchor_cell: tuple[int, int]
    occupied_cells: tuple[tuple[int, int], ...]
    founded_year: int
    state: str = "active"
    abandoned_year: int | None = None
    owner_settlement_id: str = ""
    route_id: str = ""
    source_event_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    condition: float = 1.0
    revision: int = 1
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.state not in SITE_STATES:
            raise ValueError(f"unsupported historical site state: {self.state}")
        if not self.occupied_cells:
            self.occupied_cells = (self.anchor_cell,)
        if self.anchor_cell not in self.occupied_cells:
            self.occupied_cells = (self.anchor_cell, *self.occupied_cells)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "site_type": self.site_type,
            "anchor_cell": list(self.anchor_cell),
            "occupied_cells": [list(cell) for cell in self.occupied_cells],
            "founded_year": self.founded_year,
            "state": self.state,
            "abandoned_year": self.abandoned_year,
            "owner_settlement_id": self.owner_settlement_id,
            "route_id": self.route_id,
            "source_event_ids": list(self.source_event_ids),
            "evidence_ids": list(self.evidence_ids),
            "condition": self.condition,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HistoricalSite":
        anchor = data.get("anchor_cell", [0, 0])
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", "未命名历史地点")),
            site_type=str(data.get("site_type", "ruins")),
            anchor_cell=(int(anchor[0]), int(anchor[1])),
            occupied_cells=tuple(
                (int(cell[0]), int(cell[1]))
                for cell in data.get("occupied_cells", [anchor])),
            founded_year=int(data.get("founded_year", 0)),
            state=str(data.get("state", "active")),
            abandoned_year=(
                int(data["abandoned_year"])
                if data.get("abandoned_year") is not None else None),
            owner_settlement_id=str(data.get("owner_settlement_id", "")),
            route_id=str(data.get("route_id", "")),
            source_event_ids=list(data.get("source_event_ids", [])),
            evidence_ids=list(data.get("evidence_ids", [])),
            condition=float(data.get("condition", 1.0)),
            revision=int(data.get("revision", 1)),
            schema_version=int(data.get("schema_version", 1)),
        )


@dataclass
class BurialRecord:
    id: str
    site_id: str
    person_id: str
    burial_year: int
    marker_type: str
    commissioner_person_id: str = ""
    religion_id: str = ""
    source_event_ids: list[str] = field(default_factory=list)
    inscription_evidence_id: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "site_id": self.site_id,
            "person_id": self.person_id,
            "burial_year": self.burial_year,
            "marker_type": self.marker_type,
            "commissioner_person_id": self.commissioner_person_id,
            "religion_id": self.religion_id,
            "source_event_ids": list(self.source_event_ids),
            "inscription_evidence_id": self.inscription_evidence_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BurialRecord":
        return cls(
            id=str(data["id"]),
            site_id=str(data["site_id"]),
            person_id=str(data["person_id"]),
            burial_year=int(data["burial_year"]),
            marker_type=str(data.get("marker_type", "grave_marker")),
            commissioner_person_id=str(
                data.get("commissioner_person_id", "")),
            religion_id=str(data.get("religion_id", "")),
            source_event_ids=list(data.get("source_event_ids", [])),
            inscription_evidence_id=str(
                data.get("inscription_evidence_id", "")),
            schema_version=int(data.get("schema_version", 1)),
        )


class HistoricalSiteManager:
    """Derive persistent sites from simulated facts without shared RNG use."""

    def __init__(self, seed: int,
                 sites: dict[str, HistoricalSite],
                 burials: dict[str, BurialRecord]):
        self.seed = seed
        self.sites = sites
        self.burials = burials

    def sync(self, world) -> list[BurialRecord]:
        self._sync_cemeteries(world)
        self._sync_route_sites(world)
        self._sync_event_ruins(world)
        self._sync_rural_sites(world)
        created = self._sync_burials(world)
        self._sync_abandoned_cemeteries(world)
        return created

    def _sync_cemeteries(self, world) -> None:
        occupied = {
            cell for site in self.sites.values()
            for cell in site.occupied_cells
        }
        for settlement in sorted(world.settlements.values(), key=lambda item: item.id):
            site_id = f"site_cemetery_{settlement.id}"
            state = "active" if settlement.alive else "abandoned"
            source_ids = self._settlement_source_ids(world, settlement.id)
            site = self.sites.get(site_id)
            if site is None:
                site = HistoricalSite(
                    id=site_id,
                    name=(f"{settlement.name}墓园" if settlement.alive
                          else f"废弃的{settlement.name}墓园"),
                    site_type="cemetery",
                    anchor_cell=(int(settlement.grid_x), int(settlement.grid_y)),
                    occupied_cells=((int(settlement.grid_x),
                                     int(settlement.grid_y)),),
                    founded_year=settlement.founded_year,
                    state=state,
                    abandoned_year=(world.current_year
                                    if not settlement.alive else None),
                    owner_settlement_id=settlement.id,
                    source_event_ids=source_ids,
                    condition=1.0 if settlement.alive else 0.38,
                )
                self.sites[site.id] = site
            elif site.state != state:
                site.state = state
                site.name = (f"{settlement.name}墓园" if settlement.alive
                             else f"废弃的{settlement.name}墓园")
                site.abandoned_year = world.current_year if not settlement.alive else None
                site.condition = 1.0 if settlement.alive else min(site.condition, 0.38)
                site.revision += 1
            settlement_cell = (
                int(settlement.grid_x), int(settlement.grid_y))
            has_burials = any(
                burial.site_id == site.id for burial in self.burials.values())
            if (site.anchor_cell == settlement_cell and not has_burials
                    and not self._cemetery_fits(world, settlement)):
                cell = self._nearby_cell(
                    world, settlement, "cemetery-overflow", radius=1,
                    excluded=occupied)
                if cell == settlement_cell:
                    cell = self._nearby_cell(
                        world, settlement, "cemetery-overflow", radius=3,
                        excluded=occupied)
                if cell != settlement_cell:
                    site.anchor_cell = cell
                    site.occupied_cells = (cell,)
                    site.revision += 1
            occupied.update(site.occupied_cells)

    @staticmethod
    def _cemetery_fits(world, settlement) -> bool:
        # Imported lazily to keep simulation data types independent of game UI.
        from game.local_map import LocalMapBuilder
        return LocalMapBuilder().cemetery_fits(world, settlement)

    def _sync_route_sites(self, world) -> None:
        for route in sorted(world.trade_routes.values(), key=lambda item: item.id):
            interior = route.path[1:-1]
            if not interior:
                continue
            index = _stable_int(str(self.seed), route.id, "roadside-site") % len(interior)
            cell = interior[index]
            site_type = ("roadside_inn" if len(route.path) >= 6
                         else "tollhouse")
            site_id = f"site_{site_type}_{route.id}"
            existing = self.sites.get(site_id)
            if existing is not None:
                expected_state = (
                    "active" if route.status == "active" else "abandoned")
                expected_abandoned_year = (
                    None if route.status == "active" else route.closed_year)
                if (existing.state != expected_state
                        or existing.abandoned_year != expected_abandoned_year):
                    existing.state = expected_state
                    existing.abandoned_year = expected_abandoned_year
                    existing.condition = (
                        0.9 if route.status == "active" else 0.42)
                    existing.revision += 1
                continue
            first = world.settlements.get(route.settlement_a_id)
            second = world.settlements.get(route.settlement_b_id)
            names = "与".join(item.name for item in (first, second) if item)
            self.sites[site_id] = HistoricalSite(
                id=site_id,
                name=(f"{names}商路驿站" if site_type == "roadside_inn"
                      else f"{names}商路关卡"),
                site_type=site_type,
                anchor_cell=cell,
                occupied_cells=(cell,),
                founded_year=route.opened_year,
                state=("active" if route.status == "active" else "abandoned"),
                abandoned_year=(route.closed_year
                                if route.status != "active" else None),
                owner_settlement_id=route.settlement_a_id,
                route_id=route.id,
                source_event_ids=[route.opened_event_id] if route.opened_event_id else [],
                condition=0.42 if route.status != "active" else 0.9,
            )

    def _sync_event_ruins(self, world) -> None:
        site_types = {
            "war": "battlefield_ruins",
            "raid": "burned_waystation",
            "disaster": "disaster_ruins",
            "decline": "abandoned_hamlet",
            "rebellion": "ruined_outpost",
        }
        for event in sorted(world.events, key=lambda item: (item.year, item.id)):
            site_type = site_types.get(event.event_type)
            settlement = world.settlements.get(event.primary_location)
            if site_type is None or settlement is None:
                continue
            site_id = f"site_{site_type}_{event.id}"
            if site_id in self.sites:
                continue
            anchor = self._nearby_cell(
                world, settlement, f"{site_type}|{event.id}", radius=4)
            occupied = [anchor]
            if site_type in {"battlefield_ruins", "abandoned_hamlet"}:
                extension = self._adjacent_land_cell(world, anchor, occupied)
                if extension is not None:
                    occupied.append(extension)
            self.sites[site_id] = HistoricalSite(
                id=site_id,
                name={
                    "battlefield_ruins": f"{settlement.name}旧战场",
                    "burned_waystation": f"{settlement.name}道旁焚毁遗址",
                    "disaster_ruins": f"{settlement.name}灾变遗址",
                    "abandoned_hamlet": f"{settlement.name}外围废村",
                    "ruined_outpost": f"{settlement.name}旧营垒",
                }[site_type],
                site_type=site_type,
                anchor_cell=anchor,
                occupied_cells=tuple(occupied),
                founded_year=max(settlement.founded_year, event.year - 12),
                state="ruined",
                abandoned_year=event.year,
                owner_settlement_id=settlement.id,
                source_event_ids=[event.id],
                condition=max(0.08, 0.48 - event.severity * 0.35),
            )

    def _sync_rural_sites(self, world) -> None:
        occupied = {cell for site in self.sites.values()
                    for cell in site.occupied_cells}
        for settlement in sorted(world.settlements.values(), key=lambda item: item.id):
            source_ids = self._settlement_source_ids(world, settlement.id)
            biome = str(settlement.biome)
            if biome in {"mountain", "highland"}:
                site_type, label = "mine", "旧矿场"
            elif biome == "forest":
                site_type, label = "logging_camp", "林场"
            else:
                site_type, label = "farmstead", "乡间农庄"
            site_id = f"site_{site_type}_{settlement.id}"
            if site_id not in self.sites:
                cell = self._nearby_cell(
                    world, settlement, f"rural|{site_type}", radius=3,
                    excluded=occupied)
                occupied.add(cell)
                self.sites[site_id] = HistoricalSite(
                    id=site_id,
                    name=f"{settlement.name}{label}",
                    site_type=site_type,
                    anchor_cell=cell,
                    occupied_cells=(cell,),
                    founded_year=min(world.current_year,
                                     settlement.founded_year + 8),
                    state="active" if settlement.alive else "abandoned",
                    abandoned_year=(world.current_year
                                    if not settlement.alive else None),
                    owner_settlement_id=settlement.id,
                    source_event_ids=source_ids[-2:],
                    condition=0.82 if settlement.alive else 0.3,
                )
            if settlement.infrastructure.get("fortification", 0.0) <= 0:
                continue
            watch_id = f"site_watchtower_{settlement.id}"
            if watch_id in self.sites:
                continue
            cell = self._nearby_cell(
                world, settlement, "watchtower", radius=5,
                excluded=occupied)
            occupied.add(cell)
            self.sites[watch_id] = HistoricalSite(
                id=watch_id,
                name=f"{settlement.name}外哨塔",
                site_type="watchtower",
                anchor_cell=cell,
                occupied_cells=(cell,),
                founded_year=min(world.current_year,
                                 settlement.founded_year + 12),
                state="active" if settlement.alive else "ruined",
                abandoned_year=world.current_year if not settlement.alive else None,
                owner_settlement_id=settlement.id,
                source_event_ids=source_ids[-3:],
                condition=0.85 if settlement.alive else 0.22,
            )

    def _sync_burials(self, world) -> list[BurialRecord]:
        by_person = {item.person_id for item in self.burials.values()}
        created = []
        for person in sorted(world.persons.values(), key=lambda item: item.id):
            if person.alive or person.death_year is None or person.id in by_person:
                continue
            settlement = world.settlements.get(person.settlement_id)
            if settlement is None:
                continue
            site = self._cemetery_with_capacity(world, settlement)
            related = [
                event for event in world.events
                if event.year <= person.death_year and person.id in event.person_ids
            ]
            related.sort(key=lambda item: (
                item.importance_score, item.severity, item.year, item.id),
                reverse=True)
            commissioner = self._commissioner(world, person)
            religion_id = settlement.official_religion_id if settlement else ""
            marker_type = (
                "memorial_tomb" if "ruler" in person.roles else
                "family_tombstone" if person.parent_ids or person.spouse_ids else
                "grave_marker")
            burial = BurialRecord(
                id=f"burial_{person.id}",
                site_id=site.id,
                person_id=person.id,
                burial_year=person.death_year,
                marker_type=marker_type,
                commissioner_person_id=commissioner,
                religion_id=religion_id or "",
                source_event_ids=[event.id for event in related[:6]],
            )
            self.burials[burial.id] = burial
            created.append(burial)
        return created

    def _sync_abandoned_cemeteries(self, world) -> None:
        occupied = {cell for site in self.sites.values()
                    for cell in site.occupied_cells}
        for settlement in sorted(world.settlements.values(), key=lambda item: item.id):
            old_burials = sorted((
                burial for burial in self.burials.values()
                if self.sites.get(burial.site_id) is not None
                and self.sites[burial.site_id].owner_settlement_id == settlement.id
                and burial.burial_year <= world.current_year - 35
            ), key=lambda burial: (burial.burial_year, burial.id))
            if len(old_burials) < 3:
                continue
            for offset in range(0, len(old_burials), CEMETERY_PLOT_CAPACITY):
                plot_number = offset // CEMETERY_PLOT_CAPACITY + 1
                site_id = (
                    f"site_abandoned_cemetery_{settlement.id}"
                    if plot_number == 1 else
                    f"site_abandoned_cemetery_{settlement.id}_{plot_number}")
                chunk = old_burials[offset:offset + CEMETERY_PLOT_CAPACITY]
                site = self.sites.get(site_id)
                if site is None:
                    cell = self._new_cemetery_cell(
                        world, settlement,
                        f"old-cemetery|{plot_number}", occupied)
                    occupied.add(cell)
                    source_ids = list(dict.fromkeys(
                        event_id for burial in chunk
                        for event_id in burial.source_event_ids))[-6:]
                    site = HistoricalSite(
                        id=site_id,
                        name=(f"{settlement.name}旧墓园"
                              if plot_number == 1 else
                              f"{settlement.name}旧墓园第{plot_number}区"),
                        site_type="abandoned_cemetery",
                        anchor_cell=cell,
                        occupied_cells=(cell,),
                        founded_year=min(
                            burial.burial_year for burial in chunk),
                        state="abandoned",
                        abandoned_year=max(
                            burial.burial_year for burial in chunk) + 1,
                        owner_settlement_id=settlement.id,
                        source_event_ids=source_ids,
                        condition=0.32,
                    )
                    self.sites[site.id] = site
                for burial in chunk:
                    if burial.site_id == site.id:
                        continue
                    burial.site_id = site.id
                    site.revision += 1

    def _cemetery_with_capacity(self, world, settlement) -> HistoricalSite:
        base_id = f"site_cemetery_{settlement.id}"
        plots = [
            site for site in self.sites.values()
            if site.site_type == "cemetery"
            and site.owner_settlement_id == settlement.id
        ]
        plots.sort(key=lambda site: (site.id != base_id, site.id))
        counts = {
            site.id: sum(
                burial.site_id == site.id for burial in self.burials.values())
            for site in plots
        }
        for site in plots:
            if counts[site.id] < CEMETERY_PLOT_CAPACITY:
                return site

        plot_number = len(plots) + 1
        occupied = {
            cell for site in self.sites.values()
            for cell in site.occupied_cells
        }
        cell = self._new_cemetery_cell(
            world, settlement, f"cemetery-plot|{plot_number}", occupied)
        source_ids = self._settlement_source_ids(world, settlement.id)
        site = HistoricalSite(
            id=f"{base_id}_overflow_{plot_number}",
            name=f"{settlement.name}墓园第{plot_number}区",
            site_type="cemetery",
            anchor_cell=cell,
            occupied_cells=(cell,),
            founded_year=world.current_year,
            state="active" if settlement.alive else "abandoned",
            abandoned_year=(world.current_year
                            if not settlement.alive else None),
            owner_settlement_id=settlement.id,
            source_event_ids=source_ids,
            condition=1.0 if settlement.alive else 0.38,
        )
        self.sites[site.id] = site
        return site

    def _new_cemetery_cell(
            self, world, settlement, key: str,
            excluded: set[tuple[int, int]]) -> tuple[int, int]:
        origin = (int(settlement.grid_x), int(settlement.grid_y))
        for radius in range(1, 9):
            cell = self._nearby_cell(
                world, settlement, key, radius=radius, excluded=excluded)
            if cell != origin:
                return cell
        return origin

    @staticmethod
    def _commissioner(world, person) -> str:
        preferred = [*person.spouse_ids]
        preferred.extend(
            item.id for item in world.persons.values()
            if person.id in item.parent_ids)
        preferred.extend(person.parent_ids)
        for person_id in preferred:
            candidate = world.persons.get(person_id)
            if candidate is not None and candidate.alive:
                return candidate.id
        settlement = world.settlements.get(person.settlement_id)
        if settlement is not None:
            ruler = world.persons.get(settlement.ruler_id)
            if ruler is not None and ruler.alive:
                return ruler.id
        return ""

    @staticmethod
    def _settlement_source_ids(world, settlement_id: str) -> list[str]:
        return [
            event.id for event in world.events
            if event.primary_location == settlement_id
            and event.event_type in {
                "founding", "construction", "trade", "war", "decline"}
        ][-6:]

    def _nearby_cell(self, world, settlement, key: str, radius: int,
                     excluded: set[tuple[int, int]] | None = None
                     ) -> tuple[int, int]:
        excluded = excluded or set()
        origin = (int(settlement.grid_x), int(settlement.grid_y))
        candidates = []
        for y in range(max(0, origin[1] - radius),
                       min(world.geography.height, origin[1] + radius + 1)):
            for x in range(max(0, origin[0] - radius),
                           min(world.geography.width, origin[0] + radius + 1)):
                cell = (x, y)
                distance = abs(x - origin[0]) + abs(y - origin[1])
                if distance == 0 or distance > radius or cell in excluded:
                    continue
                if str(world.geography.biomes[y, x]) in {"ocean", "lake"}:
                    continue
                if world.get_settlement_at(x, y) is not None:
                    continue
                rank = _stable_int(str(self.seed), settlement.id, key, str(x), str(y))
                candidates.append((distance, rank, cell))
        return min(candidates)[2] if candidates else origin

    @staticmethod
    def _adjacent_land_cell(world, anchor: tuple[int, int],
                            occupied: list[tuple[int, int]]
                            ) -> tuple[int, int] | None:
        for x, y in (
                (anchor[0] + 1, anchor[1]), (anchor[0], anchor[1] + 1),
                (anchor[0] - 1, anchor[1]), (anchor[0], anchor[1] - 1)):
            if not (0 <= x < world.geography.width
                    and 0 <= y < world.geography.height):
                continue
            if (x, y) in occupied:
                continue
            if str(world.geography.biomes[y, x]) not in {"ocean", "lake"}:
                return x, y
        return None


def site_signature(sites: list[HistoricalSite]) -> str:
    return "|".join(
        f"{site.id}:{site.revision}:{site.state}:{site.condition:.3f}"
        for site in sorted(sites, key=lambda item: item.id)
    )
