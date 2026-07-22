"""Build objective observations from truth-isolated evidence views."""

from game.investigation import EvidencePublicView, Observation
from narrative.evidence_describer import observation_description


OBSERVATION_TYPES = {
    "color": "color",
    "surface": "surface",
    "scale": "form",
    "mark": "mark",
    "form": "form",
    "arrangement": "form",
    "stratigraphy": "surface",
    "script": "script",
    "legibility": "script",
    "delivery": "delivery",
    "variation": "variation",
    "provenance": "provenance_trace",
}


def _observation_sentence(namespace: str, phrase: str) -> str:
    templates = {
        "material": f"可见载体材质为{phrase}。",
        "damage": f"{phrase}。",
        "color": f"整体呈{phrase}。",
        "surface": f"表面{phrase}。",
        "scale": f"{phrase}。",
        "mark": f"{phrase}。",
        "form": f"外形特征为：{phrase}。",
        "arrangement": f"构件排列显示：{phrase}。",
        "stratigraphy": f"裸露层面显示：{phrase}。",
        "script": f"书写痕迹显示：{phrase}。",
        "legibility": f"文字保存情况为：{phrase}。",
        "delivery": f"讲述方式表现为：{phrase}。",
        "variation": f"不同复述之间可观察到：{phrase}。",
        "provenance": f"保管与转移痕迹显示：{phrase}。",
    }
    return templates.get(namespace, f"可见特征：{phrase}。")


def build_evidence_observations(
        evidence: EvidencePublicView) -> tuple[Observation, ...]:
    """Convert public feature tags into non-conclusive journal entries."""
    observations = [
        Observation.create(
            evidence, "material", evidence.material,
            _observation_sentence(
                "material", observation_description(
                    "material", evidence.material)),
            method="handling",
            clarity=max(0.65, evidence.condition),
        ),
        Observation.create(
            evidence, "damage", evidence.state,
            _observation_sentence(
                "damage", observation_description("damage", evidence.state)),
            clarity=0.95,
        ),
    ]
    seen_namespaces = set()
    for tag in evidence.tags:
        namespace, separator, value = tag.partition(":")
        if (not separator or namespace == "material"
                or namespace in seen_namespaces
                or namespace not in OBSERVATION_TYPES):
            continue
        seen_namespaces.add(namespace)
        method = "listening" if evidence.evidence_type == "oral" else "visual"
        phrase = observation_description(namespace, value)
        observations.append(Observation.create(
            evidence,
            OBSERVATION_TYPES[namespace],
            value,
            _observation_sentence(namespace, phrase),
            method=method,
        ))
    return tuple(observations)
