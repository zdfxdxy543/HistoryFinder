"""Concrete technology profiles shared by events, evidence, and investigation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TechnologyProfile:
    key: str
    title: str
    artifact_subtype: str
    display_name: str
    material: str
    form_code: str
    mechanism_code: str
    function_cn: str


TECHNOLOGY_CATALOG = (
    TechnologyProfile(
        "compound_pulley", "复合滑轮吊具", "compound_pulley",
        "带多槽轮的木质滑轮组", "wood", "pulley_cluster",
        "rope_multiplier", "用多段绳索分担提升重物所需的拉力"),
    TechnologyProfile(
        "ratchet_winch", "棘轮绞盘", "ratchet_winch",
        "带棘齿的手摇绞盘", "wood", "toothed_drum",
        "reverse_stop", "让卷筒逐段收绳并阻止载荷反向坠落"),
    TechnologyProfile(
        "gear_train", "齿轮传动架", "gear_train",
        "三联齿轮传动架", "wood", "meshed_gears",
        "ratio_transfer", "用不同齿数改变转速和输出力量"),
    TechnologyProfile(
        "crank_mill", "曲柄磨粉机", "crank_mill",
        "带侧置曲柄的小型磨机", "stone", "crank_frame",
        "rotary_drive", "把往复摇动转为连续旋转"),
    TechnologyProfile(
        "seed_drill", "定距排种器", "seed_drill",
        "带等距落种孔的木制排种器", "wood", "spaced_tubes",
        "measured_seed", "按固定间隔和近似数量把种粒送入沟内"),
    TechnologyProfile(
        "adjustable_plough", "可调深沟犁", "adjustable_plough",
        "带多档销孔的铁犁头", "metal", "adjustable_blade",
        "depth_control", "借助销孔调节犁刃入土深度"),
    TechnologyProfile(
        "sluice_gate_model", "水渠闸门样机", "sluice_gate_model",
        "可升降的槽式闸门样机", "wood", "slotted_gate",
        "flow_control", "用分档闸板控制支渠水量"),
    TechnologyProfile(
        "chain_pump", "链斗提水机", "chain_pump",
        "带连续木斗的提水链架", "wood", "linked_cups",
        "continuous_lift", "让相连容器循环经过低处并提升水流"),
    TechnologyProfile(
        "sealed_cistern", "封闭式蓄水槽", "sealed_cistern_model",
        "带封泥接口的蓄水槽模型", "stone", "sealed_channels",
        "evaporation_control", "减少储水暴露并分离取水口与沉淀区"),
    TechnologyProfile(
        "ventilated_granary", "通风粮柜", "ventilated_granary_model",
        "带架空风道的粮柜模型", "wood", "vented_chambers",
        "dry_airflow", "让空气从粮层下方通过以减轻受潮"),
    TechnologyProfile(
        "precision_balance", "标准药材秤", "precision_balance",
        "带成组砝码的细梁药秤", "metal", "graduated_balance",
        "repeatable_measure", "用统一砝码重复称量少量药材"),
    TechnologyProfile(
        "surgical_kit", "清创器械组", "surgical_kit",
        "可煮洗的成套清创器械", "metal", "nested_instruments",
        "cleanable_tools", "把切开、夹取和缝合工具分开保存并清洗"),
    TechnologyProfile(
        "distillation_coil", "冷凝蒸馏器", "distillation_coil",
        "带弯曲冷凝管的蒸馏器", "metal", "coiled_condenser",
        "vapor_condensation", "引导热蒸气经过冷却管并重新凝结"),
    TechnologyProfile(
        "double_chamber_furnace", "双层炉膛", "double_chamber_furnace_model",
        "上下分隔的双层炉膛模型", "stone", "separated_chambers",
        "controlled_draft", "把燃料与工件分层并引导空气通过炉床"),
    TechnologyProfile(
        "arch_centering_frame", "石拱定心架", "arch_centering_frame",
        "可拆卸的弧形定心木架", "wood", "radial_ribs",
        "temporary_support", "在拱券闭合前临时承托各块拱石"),
    TechnologyProfile(
        "star_sighting_instrument", "星位定向仪", "star_sighting_instrument",
        "带转动照准片的星位仪", "metal", "sighting_vanes",
        "angular_sighting", "以照准片和刻度重复比较星体高度"),
)


TECHNOLOGY_BY_SUBTYPE = {
    profile.artifact_subtype: profile for profile in TECHNOLOGY_CATALOG
}
TECHNOLOGY_ARTIFACT_SUBTYPES = frozenset(TECHNOLOGY_BY_SUBTYPE)
