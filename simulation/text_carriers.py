"""Lazy rule-based text materialization and persistent carrier damage."""

from __future__ import annotations

import copy
import hashlib
import threading

from simulation.written_content import (
    PUBLIC_INSCRIPTION_SUBTYPES,
    build_written_content,
    build_written_copy_content,
)


TEXT_PLAN_VERSION = 1
MATERIALIZED_TEXT_VERSION = 3
PAGE_CHARACTER_BUDGET = 700

_LOCKS_GUARD = threading.Lock()
_WORK_LOCKS: dict[tuple[int, str], threading.RLock] = {}


DAMAGE_TYPES = {
    "parchment": (
        "faded_ink", "water_blur", "insect_holes", "torn_edge",
        "missing_leaf",
    ),
    "paper": (
        "faded_ink", "water_blur", "torn_edge", "stuck_pages",
        "missing_leaf",
    ),
    "wood": (
        "worn_surface", "split_surface", "rot", "flaked_surface",
    ),
    "stone": (
        "weathering", "crack", "spalling", "worn_surface",
    ),
    "metal": (
        "corrosion", "worn_surface", "bent_surface", "flaked_surface",
    ),
}


DAMAGE_LABELS = {
    "faded_ink": "字迹褪色",
    "water_blur": "水渍模糊",
    "insect_holes": "虫蛀缺损",
    "torn_edge": "页边缺失",
    "missing_leaf": "中间一叶脱落",
    "stuck_pages": "纸页粘连",
    "worn_surface": "表面磨损",
    "split_surface": "木板开裂",
    "rot": "腐朽缺损",
    "flaked_surface": "表层脱落",
    "weathering": "刻痕风化",
    "crack": "裂缝穿过文字",
    "spalling": "石面剥落",
    "corrosion": "锈蚀遮盖",
    "bent_surface": "弯折处不可辨",
    "combined": "多处损伤重叠",
}


def _stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def _base_subtype(evidence) -> str:
    return evidence.subtype.removesuffix("_copy") \
        if evidence.is_copy_of else evidence.subtype


def has_text_carrier(evidence) -> bool:
    """Whether this physical carrier has or can materialize written words."""
    return bool(
        evidence.content_data.get("written_content")
        or evidence.content_data.get("text_plan")
    )


def make_text_plan(world_seed: int, evidence_id: str, event_id: str,
                   subtype: str, created_year: int,
                   parent_evidence_id: str | None = None,
                   copy_index: int | None = None,
                   ready: bool = False) -> dict:
    root_id = parent_evidence_id or evidence_id
    return {
        "format_version": TEXT_PLAN_VERSION,
        "work_id": f"work:{root_id}",
        "root_evidence_id": root_id,
        "parent_evidence_id": parent_evidence_id,
        "subtype": subtype,
        "generation_seed": world_seed,
        "generation_variant": 0,
        "copy_index": copy_index,
        "created_year": created_year,
        "materialization_status": "ready" if ready else "planned",
        "generator_kind": "rules",
        "prompt_version": "rules-v1",
        "composition_signature": hashlib.sha256(
            f"{world_seed}|{event_id}|{subtype}|{evidence_id}".encode("utf-8")
        ).hexdigest()[:20],
    }


def initialize_text_plan(evidence, world_seed: int,
                         copy_index: int | None = None,
                         ready: bool | None = None) -> dict:
    """Attach a stable plan without replacing already persisted text."""
    plan = evidence.content_data.get("text_plan")
    if plan:
        return plan
    if ready is None:
        ready = bool(evidence.content_data.get("written_content"))
    plan = make_text_plan(
        world_seed, evidence.id, evidence.event_id, evidence.subtype,
        evidence.created_year, evidence.is_copy_of, copy_index, ready)
    evidence.content_data["text_plan"] = plan
    return plan


def _work_lock(world, root_id: str) -> threading.RLock:
    key = (id(world), root_id)
    with _LOCKS_GUARD:
        return _WORK_LOCKS.setdefault(key, threading.RLock())


def _normalize_passages(written: dict, evidence_id: str,
                        parent_written: dict | None = None) -> dict:
    result = copy.deepcopy(written)
    result["format_version"] = MATERIALIZED_TEXT_VERSION
    parent_passages = (
        parent_written.get("passages", ()) if parent_written else ())
    normalized = []
    for index, passage in enumerate(result.get("passages", ())):
        item = dict(passage)
        source_id = item.get("source_section_id")
        if source_id is None and index < len(parent_passages):
            source_id = parent_passages[index].get("source_section_id") \
                or parent_passages[index].get("section_id")
        if source_id is None and parent_written is None:
            source_id = f"source:{evidence_id}:{index:03d}"
        item["source_section_id"] = source_id
        item["section_id"] = f"section:{evidence_id}:{index:03d}"
        normalized.append(item)
    result["passages"] = normalized
    return result


def _transmission_variants(parent_written: dict, copy_written: dict) -> list[dict]:
    parent = parent_written.get("passages", ())
    copied = copy_written.get("passages", ())
    variants = []
    for index, passage in enumerate(copied):
        if index >= len(parent):
            variants.append({
                "variant_type": passage.get("kind", "addition"),
                "section_id": passage.get("section_id"),
                "source_section_id": passage.get("source_section_id"),
            })
        elif passage.get("text") != parent[index].get("text"):
            variants.append({
                "variant_type": "altered_or_lacuna",
                "section_id": passage.get("section_id"),
                "source_section_id": passage.get("source_section_id"),
            })
    return variants


def _content_hash(written: dict) -> str:
    text = "\n".join(
        passage.get("text", "")
        for passage in written.get("passages", ()))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _body_units(written: dict) -> set[str]:
    return {
        "".join(passage.get("text", "").split())
        for passage in written.get("passages", ())
        if passage.get("kind") not in {
            "heading", "attribution", "closing", "copy_note", "marginalia",
        }
        and len("".join(passage.get("text", "").split())) >= 12
    }


def _acceptable_original(world, evidence, written: dict) -> bool:
    fingerprint = _content_hash(written)
    candidate_units = _body_units(written)
    source_event = world.get_event(evidence.event_id)
    grounded_history_work = bool(
        source_event is not None
        and source_event.details.get("genre") in {"chronicle", "biography"}
    )
    diversity_checked_subtypes = {
        "literary_manuscript",
        "traveling_literary_copy",
        "theoretical_treatise",
    }
    for other in world.evidence.values():
        if other.id == evidence.id or other.is_copy_of:
            continue
        other_written = other.content_data.get("written_content")
        if not other_written:
            continue
        if fingerprint == _content_hash(other_written):
            return False
        if _base_subtype(other) != _base_subtype(evidence):
            continue
        if _base_subtype(evidence) not in diversity_checked_subtypes:
            continue
        # Grounded histories may legitimately quote the same frozen event in
        # later editions. Requiring low paragraph overlap would force filler.
        if grounded_history_work:
            continue
        other_units = _body_units(other_written)
        if not candidate_units or not other_units:
            continue
        if min(len(candidate_units), len(other_units)) < 4:
            continue
        overlap = len(candidate_units & other_units) / max(
            1, len(candidate_units | other_units))
        if overlap > 0.25:
            return False
    if _base_subtype(evidence) in {
            "literary_manuscript", "traveling_literary_copy"}:
        full_text = "".join(
            passage.get("text", "")
            for passage in written.get("passages", ()))
        if any(marker in full_text for marker in (
                "本书讲述", "本章讨论", "第一歌讲述", "第一卷追索")):
            return False
    return True


def _build_layout(written: dict) -> dict:
    pages = []
    current = {"page_index": 0, "character_count": 0, "section_spans": []}
    for passage in written.get("passages", ()):
        text = passage.get("text", "")
        if (current["section_spans"]
                and current["character_count"] + len(text)
                > PAGE_CHARACTER_BUDGET):
            pages.append(current)
            current = {
                "page_index": len(pages),
                "character_count": 0,
                "section_spans": [],
            }
        current["section_spans"].append({
            "section_id": passage["section_id"],
            "start": 0,
            "end": len(text),
        })
        current["character_count"] += len(text)
    if current["section_spans"] or not pages:
        pages.append(current)
    return {
        "format_version": 1,
        "page_count": len(pages),
        "pages": pages,
    }


def _condition_ratio(evidence) -> float:
    if evidence.max_durability <= 0:
        return 0.0
    return max(0.0, min(
        1.0, evidence.current_durability / evidence.max_durability))


def _target_loss_ratio(condition: float) -> float:
    if condition >= 0.85:
        return 0.0
    normalized = (0.85 - condition) / 0.85
    return min(0.60, 0.60 * normalized * normalized)


def _active_damage_type(material: str, condition: float,
                        ordinal: int) -> str:
    options = DAMAGE_TYPES.get(material, DAMAGE_TYPES["parchment"])
    eligible = list(options[:2])
    if condition < 0.65:
        eligible.extend(options[2:4])
    if condition < 0.25 and len(options) > 4:
        eligible.append(options[4])
    return eligible[ordinal % len(eligible)]


def _covered_characters(lesions: list[dict]) -> int:
    by_section: dict[str, list[tuple[int, int]]] = {}
    for lesion in lesions:
        by_section.setdefault(lesion["section_id"], []).append(
            (int(lesion["start"]), int(lesion["end"])))
    total = 0
    for spans in by_section.values():
        cursor = -1
        for start, end in sorted(spans):
            if end <= cursor:
                continue
            total += end - max(start, cursor)
            cursor = end
    return total


def advance_text_damage(evidence) -> dict | None:
    """Grow a carrier's persistent damage map to its current condition."""
    written = evidence.content_data.get("written_content")
    layout = evidence.content_data.get("text_layout")
    if not written or not layout:
        return None
    passages = {
        passage["section_id"]: passage
        for passage in written.get("passages", ())
    }
    total_chars = sum(len(item.get("text", "")) for item in passages.values())
    condition = _condition_ratio(evidence)
    state = evidence.content_data.setdefault("damage_state", {
        "format_version": 1,
        "condition_checkpoint": 1.0,
        "damage_seed": _stable_int(evidence.id, "damage"),
        "lesions": [],
    })
    checkpoint = float(state.get("condition_checkpoint", 1.0))
    if condition >= checkpoint:
        return state

    lesions = state.setdefault("lesions", [])
    target = round(total_chars * _target_loss_ratio(condition))
    covered = _covered_characters(lesions)
    candidates = [
        (page["page_index"], span["section_id"])
        for page in layout.get("pages", ())
        for span in page.get("section_spans", ())
        if len(passages.get(span["section_id"], {}).get("text", "")) > 0
    ]
    ordinal = len(lesions)
    attempts = 0
    while covered < target and candidates and attempts < max(200, target * 8):
        page_index, section_id = candidates[
            _stable_int(evidence.id, "damage-section", ordinal) % len(candidates)]
        text = passages[section_id].get("text", "")
        remaining = target - covered
        chunk_cap = max(1, round(total_chars * (
            0.008 if condition >= 0.65 else
            0.018 if condition >= 0.35 else 0.035)))
        length = min(len(text), remaining, chunk_cap)
        available = max(1, len(text) - length + 1)
        start = _stable_int(
            evidence.id, "damage-start", ordinal) % available
        end = min(len(text), start + length)
        before = covered
        damage_type = _active_damage_type(
            evidence.material, condition, ordinal)
        lesions.append({
            "lesion_id": f"lesion:{evidence.id}:{ordinal:04d}",
            "damage_type": damage_type,
            "page_index": page_index,
            "section_id": section_id,
            "start": start,
            "end": end,
            "severity": round(1.0 - condition, 4),
            "activation_condition": round(condition, 4),
            "reversible": damage_type in {
                "faded_ink", "water_blur", "weathering", "corrosion",
                "worn_surface",
            },
        })
        covered = _covered_characters(lesions)
        if covered == before:
            lesions.pop()
        ordinal += 1
        attempts += 1
    state["condition_checkpoint"] = condition
    state["covered_characters"] = covered
    state["total_characters"] = total_chars
    return state


def prepare_materialized_carrier(evidence, written: dict,
                                 parent_written: dict | None = None) -> dict:
    normalized = _normalize_passages(
        written, evidence.id, parent_written=parent_written)
    evidence.content_data["written_content"] = normalized
    if parent_written is not None:
        evidence.content_data["transmission_variants"] = \
            _transmission_variants(parent_written, normalized)
    else:
        evidence.content_data["transmission_variants"] = []
    evidence.content_data["text_layout"] = _build_layout(normalized)
    evidence.content_data.pop("damage_state", None)
    advance_text_damage(evidence)
    plan = evidence.content_data.get("text_plan")
    if plan is not None:
        plan["materialization_status"] = "ready"
    return normalized


def materialize_text_carrier(world, evidence_id: str) -> object:
    """Materialize a root before deriving any requested copy."""
    evidence = world.evidence.get(evidence_id)
    if evidence is None or not has_text_carrier(evidence):
        raise ValueError(f"evidence {evidence_id} is not a written carrier")
    plan = initialize_text_plan(evidence, world.seed)
    root_id = plan.get("root_evidence_id") or evidence.is_copy_of or evidence.id
    lock = _work_lock(world, root_id)
    with lock:
        if evidence.content_data.get("written_content"):
            # Persisted version 1/2 carriers retain their original structure
            # and continue through the legacy reader.  Only newly generated
            # version 3 carriers own a layout and persistent damage map.
            if evidence.content_data.get("text_layout"):
                advance_text_damage(evidence)
            return evidence

        plan["materialization_status"] = "generating"
        try:
            parent_written = None
            if evidence.is_copy_of:
                parent = materialize_text_carrier(world, evidence.is_copy_of)
                parent_written = parent.content_data["written_content"]
                copy_index = int(plan.get("copy_index") or 0)
                written = build_written_copy_content(
                    parent_written,
                    int(plan.get("generation_seed", world.seed)),
                    evidence.id,
                    copy_index,
                    evidence.created_year,
                    variant=int(plan.get("generation_variant", 0)),
                )
            else:
                event = world.get_event(evidence.event_id)
                if event is None:
                    raise ValueError(
                        f"source event {evidence.event_id} is unavailable")
                first_variant = int(plan.get("generation_variant", 0))
                written = None
                for variant in range(first_variant, first_variant + 64):
                    candidate = build_written_content(
                        event,
                        _base_subtype(evidence),
                        int(plan.get("generation_seed", world.seed)),
                        evidence.id,
                        variant=variant,
                    )
                    if _acceptable_original(world, evidence, candidate):
                        written = candidate
                        plan["generation_variant"] = variant
                        break
                if written is None:
                    raise RuntimeError(
                        f"could not create distinct text for {evidence.id}")
            prepare_materialized_carrier(
                evidence, written, parent_written=parent_written)
            plan["content_hash"] = _content_hash(
                evidence.content_data["written_content"])
            return evidence
        except Exception:
            plan["materialization_status"] = "failed"
            raise


def render_damaged_passages(evidence) -> tuple[list[str], float]:
    """Render current visible text without exposing hidden damaged spans."""
    written = evidence.content_data.get("written_content", {})
    advance_text_damage(evidence)
    lesions = evidence.content_data.get("damage_state", {}).get("lesions", ())
    by_section: dict[str, list[dict]] = {}
    for lesion in lesions:
        by_section.setdefault(lesion["section_id"], []).append(lesion)
    visible = []
    total = 0
    hidden = 0
    for passage in written.get("passages", ()):
        text = passage.get("text", "")
        total += len(text)
        spans = sorted(
            by_section.get(passage.get("section_id"), ()),
            key=lambda item: (int(item["start"]), int(item["end"])))
        merged = []
        for lesion in spans:
            item = dict(lesion)
            item["damage_types"] = {item.get("damage_type", "")}
            if (merged and int(item["start"]) <= int(merged[-1]["end"]) + 1):
                merged[-1]["end"] = max(
                    int(merged[-1]["end"]), int(item["end"]))
                merged[-1]["damage_types"].update(item["damage_types"])
            else:
                merged.append(item)
        spans = merged
        if not spans:
            visible.append(text)
            continue
        rendered = []
        cursor = 0
        for lesion in spans:
            start = max(cursor, int(lesion["start"]))
            end = min(len(text), int(lesion["end"]))
            if end <= start:
                continue
            rendered.append(text[cursor:start])
            damage_types = lesion.get("damage_types", set())
            damage_type = (
                next(iter(damage_types)) if len(damage_types) == 1
                else "combined")
            label = DAMAGE_LABELS.get(damage_type, "此处缺损")
            rendered.append(f"〔{label}〕")
            hidden += end - start
            cursor = end
        rendered.append(text[cursor:])
        visible.append("".join(rendered))
    readability = 1.0 if total <= 0 else max(0.0, 1.0 - hidden / total)
    return visible, readability
