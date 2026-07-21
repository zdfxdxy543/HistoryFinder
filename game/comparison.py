"""Deterministic comparison of player-observable evidence properties."""

from __future__ import annotations

from collections.abc import Iterable

from game.investigation import (
    ComparisonResult,
    EvidencePublicView,
    Observation,
    stable_investigation_id,
)


OBSERVATION_LABELS = {
    "material": "材质",
    "color": "颜色",
    "surface": "表面",
    "mark": "痕迹",
    "form": "形制",
    "script": "书写",
    "damage": "保存状态",
    "delivery": "讲述方式",
    "variation": "复述差异",
}


class ComparisonEngine:
    """Compare investigation DTOs without access to world or event truth."""

    def compare(
            self, first: EvidencePublicView, second: EvidencePublicView,
            first_observations: Iterable[Observation] = (),
            second_observations: Iterable[Observation] = (),
            first_source_groups: Iterable[str] = (),
            second_source_groups: Iterable[str] = (),
            method: str = "visual") -> ComparisonResult:
        if first.id == second.id:
            raise ValueError("comparison requires two different evidence items")

        first_observations = tuple(sorted(
            first_observations, key=lambda item: item.id))
        second_observations = tuple(sorted(
            second_observations, key=lambda item: item.id))
        first_groups = tuple(sorted(set(first_source_groups)))
        second_groups = tuple(sorted(set(second_source_groups)))

        if second.id < first.id:
            first, second = second, first
            first_observations, second_observations = (
                second_observations, first_observations)
            first_groups, second_groups = second_groups, first_groups

        similarities = []
        differences = []
        if first.material == second.material:
            similarities.append(f"两件证物的可见材质都是{first.material}。")
        else:
            differences.append(
                f"材质不同：{first.observed_name}为{first.material}，"
                f"{second.observed_name}为{second.material}。")

        if first.evidence_type == second.evidence_type:
            similarities.append(
                f"两者都属于可按{first.evidence_type}方式检查的载体。")
        else:
            differences.append(
                f"载体类型不同：{first.observed_name}为{first.evidence_type}，"
                f"{second.observed_name}为{second.evidence_type}。")

        condition_gap = abs(first.condition - second.condition)
        if condition_gap <= 0.10:
            similarities.append("两者的整体保存程度接近。")
        else:
            differences.append(
                f"保存程度不同：{first.observed_name}约为{first.condition:.0%}，"
                f"{second.observed_name}约为{second.condition:.0%}。")

        first_features = self._features(first_observations)
        second_features = self._features(second_observations)
        for observation_type in sorted(set(first_features) & set(second_features)):
            first_values = first_features[observation_type]
            second_values = second_features[observation_type]
            shared = sorted(set(first_values) & set(second_values))
            label = OBSERVATION_LABELS.get(
                observation_type, observation_type)
            if shared and observation_type not in {"material", "damage"}:
                similarities.append(
                    f"两者在{label}观察中共有特征："
                    f"{self._descriptions(first_values, shared)}。")
            if not shared and first_values and second_values:
                differences.append(
                    f"{label}观察不同：{first.observed_name}记录为"
                    f"{self._descriptions(first_values)}，"
                    f"{second.observed_name}记录为"
                    f"{self._descriptions(second_values)}。")

        first_group_set = set(first_groups)
        second_group_set = set(second_groups)
        if first_group_set & second_group_set:
            source_relation = "same"
            source_note = (
                "调查日志表明两者共享已知来源谱系，因此不能算作两个独立来源。")
        elif first_group_set and second_group_set:
            source_relation = "different"
            source_note = (
                "调查日志把两者归入不同来源组，但这不表示其中主张必然一致或冲突。")
        else:
            source_relation = "unknown"
            source_note = "现有调查日志不足以判断两者是否共享来源谱系。"

        observation_ids = tuple(
            item.id for item in (*first_observations, *second_observations))
        result_id = stable_investigation_id(
            "comparison", (
                first.id, second.id, method,
                first.state, second.state,
                f"{first.condition:.6f}", f"{second.condition:.6f}",
                *observation_ids, *first_groups, *second_groups,
            ))
        return ComparisonResult(
            id=result_id,
            evidence_ids=(first.id, second.id),
            method=method,
            similarities_cn=tuple(similarities),
            differences_cn=tuple(differences),
            limitations_cn=(
                source_note,
                "外观或材料相似只能作为后续核查线索，不能单独证明共同历史归属。",
            ),
            source_group_relation=source_relation,
            observation_ids=observation_ids,
        )

    @staticmethod
    def _features(
            observations: tuple[Observation, ...]
            ) -> dict[str, dict[str, str]]:
        features: dict[str, dict[str, str]] = {}
        for observation in observations:
            features.setdefault(observation.observation_type, {}).setdefault(
                observation.value, observation.description_cn)
        return features

    @staticmethod
    def _descriptions(values: dict[str, str],
                      selected: list[str] | None = None) -> str:
        selected = sorted(values) if selected is None else selected
        return "；".join(
            values[value].rstrip("。") for value in selected)
