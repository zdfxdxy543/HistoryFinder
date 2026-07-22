"""Technology-specific research paths frozen into discovery events."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import DATA_DIR
from simulation.technology import TECHNOLOGY_CATALOG, TechnologyProfile


RESEARCH_CATALOG_PATH = Path(DATA_DIR) / "research_catalog.json"
RESEARCH_PROCESS_VERSION = 1


@dataclass(frozen=True)
class FailureMode:
    id: str
    stage: str
    description: str
    fixes: tuple[str, ...]


@dataclass(frozen=True)
class ResearchProfile:
    technology_key: str
    materials: tuple[str, ...]
    attempt_range: tuple[int, int]
    failure_modes: tuple[FailureMode, ...]
    partial_successes: tuple[str, ...]
    success_indicators: tuple[str, ...]


def _string_list(value: Any, field_name: str, technology_key: str) -> tuple[str, ...]:
    if (not isinstance(value, list) or not value
            or any(not isinstance(item, str) or not item.strip()
                   for item in value)):
        raise ValueError(
            f"research catalog {technology_key}.{field_name} must be a non-empty string list")
    return tuple(item.strip() for item in value)


def load_research_catalog(
        path: Path = RESEARCH_CATALOG_PATH) -> dict[str, ResearchProfile]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported research catalog schema_version")
    technologies = payload.get("technologies")
    if not isinstance(technologies, dict):
        raise ValueError("research catalog technologies must be an object")

    expected = {technology.key for technology in TECHNOLOGY_CATALOG}
    actual = set(technologies)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"research catalog key mismatch; missing={missing}, extra={extra}")

    result: dict[str, ResearchProfile] = {}
    for technology_key, raw in technologies.items():
        if not isinstance(raw, dict):
            raise ValueError(f"research catalog {technology_key} must be an object")
        attempt_range = raw.get("attempt_range")
        if (not isinstance(attempt_range, list) or len(attempt_range) != 2
                or any(not isinstance(item, int) for item in attempt_range)
                or not 1 <= attempt_range[0] <= attempt_range[1] <= 8):
            raise ValueError(
                f"research catalog {technology_key}.attempt_range is invalid")

        raw_modes = raw.get("failure_modes")
        if not isinstance(raw_modes, list) or not raw_modes:
            raise ValueError(
                f"research catalog {technology_key}.failure_modes must be non-empty")
        modes = []
        seen_ids: set[str] = set()
        for raw_mode in raw_modes:
            if not isinstance(raw_mode, dict):
                raise ValueError(
                    f"research catalog {technology_key} has an invalid failure mode")
            mode_id = raw_mode.get("id")
            stage = raw_mode.get("stage")
            description = raw_mode.get("description")
            if (not isinstance(mode_id, str) or not mode_id
                    or mode_id in seen_ids
                    or not isinstance(stage, str) or not stage
                    or not isinstance(description, str) or not description):
                raise ValueError(
                    f"research catalog {technology_key} has an invalid failure mode")
            seen_ids.add(mode_id)
            modes.append(FailureMode(
                id=mode_id,
                stage=stage,
                description=description,
                fixes=_string_list(
                    raw_mode.get("fixes"), "failure_modes.fixes", technology_key),
            ))

        result[technology_key] = ResearchProfile(
            technology_key=technology_key,
            materials=_string_list(raw.get("materials"), "materials", technology_key),
            attempt_range=(attempt_range[0], attempt_range[1]),
            failure_modes=tuple(modes),
            partial_successes=_string_list(
                raw.get("partial_successes"), "partial_successes", technology_key),
            success_indicators=_string_list(
                raw.get("success_indicators"), "success_indicators", technology_key),
        )
    return result


RESEARCH_CATALOG = load_research_catalog()


def generate_research_process(
        seed: int, event_id: str, technology: TechnologyProfile,
        completed_year: int, settlement_id: str, settlement_name: str,
        researcher_id: str, researcher_name: str) -> dict[str, Any]:
    """Choose a reproducible development history before any text is read."""
    profile = RESEARCH_CATALOG[technology.key]
    rng = random.Random(
        f"{seed}|{event_id}|{technology.key}|research-process-v1")
    attempt_count = rng.randint(*profile.attempt_range)
    started_year = max(0, completed_year - attempt_count + 1)
    failure_modes = list(profile.failure_modes)
    rng.shuffle(failure_modes)

    attempts = []
    for index in range(attempt_count):
        number = index + 1
        attempt_year = min(completed_year, started_year + index)
        is_final = number == attempt_count
        if is_final:
            attempts.append({
                "attempt_number": number,
                "year": attempt_year,
                "stage": "复现检查",
                "result": "repeatable_success",
                "observation": rng.choice(profile.success_indicators),
                "performed_by": researcher_name,
            })
            continue

        mode = failure_modes[index % len(failure_modes)]
        is_partial = (
            attempt_count >= 3
            and number == attempt_count - 1
            and rng.random() < 0.7
        )
        attempts.append({
            "attempt_number": number,
            "year": attempt_year,
            "stage": mode.stage,
            "result": "partial_success" if is_partial else "failure",
            "failure_id": mode.id,
            "observation": (
                rng.choice(profile.partial_successes)
                if is_partial else mode.description
            ),
            "change_for_next_attempt": rng.choice(mode.fixes),
            "performed_by": researcher_name,
        })

    return {
        "schema_version": RESEARCH_PROCESS_VERSION,
        "technology_key": technology.key,
        "technology_name": technology.title,
        "settlement_id": settlement_id,
        "settlement_name": settlement_name,
        "lead_researcher_id": researcher_id,
        "lead_researcher_name": researcher_name,
        "started_year": started_year,
        "completed_year": completed_year,
        "materials": list(profile.materials),
        "attempt_count": attempt_count,
        "attempts": attempts,
        "final_status": "repeatable_success",
    }
