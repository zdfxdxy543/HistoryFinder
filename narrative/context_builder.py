"""
上下文构建器：从模拟数据构建 LLM 所需的上下文信息。
"""

from simulation.world import World
from simulation.settlement import Settlement
from simulation.evidence import Evidence


def build_settlement_context(world: World, settlement: Settlement) -> dict:
    """
    构建聚落场景的上下文数据，供 LLM prompt 模板使用。
    """
    evidence = world.get_all_visible_evidence(settlement.id)

    evidence_summary = _format_evidence_list(evidence, max_count=10)

    if settlement.alive:
        alive_text = (
            f"It is currently a thriving {settlement.size} "
            f"with a population of {settlement.population}."
        )
    else:
        alive_text = "It is uninhabited; the date and cause are not established."

    return {
        "settlement_name": settlement.name,
        "settlement_size": settlement.size,
        "biome": world.geography.get_biome_name(settlement.grid_x, settlement.grid_y),
        "current_year": world.current_year,
        "alive_text": alive_text,
        "evidence_summary": evidence_summary,
        "ruler_name": settlement.ruler_name,
        "population": settlement.population,
        "alive": settlement.alive,
    }


def build_ruin_context(world: World, settlement: Settlement) -> dict:
    """
    构建废墟场景的上下文数据。
    """
    evidence = world.get_all_visible_evidence(settlement.id)
    evidence_summary = _format_evidence_list(evidence, max_count=10)

    return {
        "settlement_name": settlement.name,
        "settlement_size": settlement.size,
        "biome": world.geography.get_biome_name(settlement.grid_x, settlement.grid_y),
        "evidence_summary": evidence_summary,
    }


def build_evidence_context(evidence: Evidence) -> dict:
    """
    构建单个证据的玩家可见上下文。

    历史真相不得进入检查上下文。
    """
    state_desc = {
        "intact": "Well-preserved, almost as it was when created",
        "weathered": "Showing clear signs of age and exposure",
        "ruined": "Badly damaged, barely recognizable",
        "buried": "Buried underground, protected from the elements",
    }

    return {
        "evidence_type": evidence.evidence_type,
        "observed_name": evidence.physical_features.get(
            "display_name", evidence.subtype.replace("_", " ")),
        "material": evidence.material,
        "state": state_desc.get(evidence.state, evidence.state),
        "state_key": evidence.state,
        "condition_ratio": (
            evidence.current_durability / evidence.max_durability
            if evidence.max_durability > 0 else 0.0
        ),
        "physical_features": dict(evidence.physical_features),
    }


def build_location_investigation_context(world: World, location_id: str) -> dict:
    """
    构建"调查当前地点"的上下文。
    """
    stl = world.get_settlement(location_id)
    if stl is None:
        return _build_generic_location_context(world, location_id)

    evidence = world.get_all_visible_evidence(location_id)
    geo = world.geography

    return {
        "location_name": stl.name,
        "location_type": "ruin" if not stl.alive else f"{stl.size}",
        "biome": geo.get_biome_name(stl.grid_x, stl.grid_y),
        "alive_text": (
            f"It is a living {stl.size} with {stl.population} inhabitants."
            if stl.alive else
            "It is uninhabited; the date and cause are not established."
        ),
        "evidence_summary": _format_evidence_list(evidence, max_count=15),
    }


def _build_generic_location_context(world: World, location_id: str) -> dict:
    """非聚落地点的上下文（如野外 grid 格）。"""
    parts = location_id.split(",")
    if len(parts) == 2:
        x, y = int(parts[0]), int(parts[1])
        biome = world.geography.get_biome_name(x, y)
    else:
        biome = "unknown"

    evidence = world.get_all_visible_evidence(location_id)

    return {
        "location_name": f"the {biome}",
        "location_type": "wilderness",
        "biome": biome,
        "alive_text": "This is an uninhabited area.",
        "evidence_summary": _format_evidence_list(evidence, max_count=10),
    }


# ---- 格式化辅助 ----

def _format_evidence_list(evidence: list[Evidence], max_count: int = 10) -> str:
    if not evidence:
        return "No visible evidence found here."
    lines = []
    for e in evidence[:max_count]:
        state_mark = ""
        if e.state == "weathered":
            state_mark = " [weathered]"
        elif e.state == "ruined":
            state_mark = " [ruined]"
        display_name = e.physical_features.get(
            "display_name", e.subtype.replace("_", " "))
        lines.append(f"- {display_name} ({e.material}){state_mark}")
    if len(evidence) > max_count:
        lines.append(f"  (...and {len(evidence) - max_count} more items)")
    return "\n".join(lines)
