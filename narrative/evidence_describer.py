"""标签驱动的无 LLM 证物描述器。"""

import hashlib


PHRASES = {
    "material": {
        "stone": "石材", "metal": "金属", "parchment": "羊皮纸",
        "wood": "木材", "cloth": "织物", "oral": "口述材料",
    },
    "color": {
        "gray_white": "灰白色", "blue_gray": "青灰色", "ochre": "黄褐色",
        "dark_gray": "深灰色", "dark_brown": "暗褐色", "black_gray": "黑灰色",
        "rust_red": "红褐色", "mottled_green": "斑驳绿锈色",
        "dark_yellow": "暗黄色", "gray_brown": "灰褐色",
        "light_brown": "淡褐色", "blackened_ivory": "边缘发黑的黄白色",
        "deep_brown": "深褐色", "ash_gray": "灰黑色", "char_black": "焦黑色",
        "faded_tan": "褪色的浅褐色", "faded_indigo": "褪色的靛蓝色",
        "dark_red_brown": "暗红褐色", "gray_white": "灰白色",
        "muted_green": "难以辨认的暗绿色", "unknown": "难以判断的颜色",
    },
    "surface": {
        "coarse_grain": "颗粒粗粝", "fine_chisel_marks": "有细密凿痕",
        "worn_smooth": "局部被磨得平滑", "jagged_break": "边缘呈不规则断口",
        "pitted_corrosion": "布满点状锈蚀", "hammer_pattern": "仍能看见锻打纹",
        "blunted_edges": "边缘因磨损而发钝", "oxide_crust": "覆盖着不均匀的氧化壳",
        "visible_fibers": "纤维纹理清晰", "dry_wrinkles": "因干燥而起皱",
        "brittle_folds": "折痕处已经变脆", "faint_sheen": "一面仍保留轻微光泽",
        "visible_grain": "木纹仍可辨认", "flaking_surface": "表层呈片状剥落",
        "softened_core": "内部已经变得疏松", "charred_side": "一侧有明显炭化",
        "frayed_fibers": "纤维已经起毛", "regular_weave": "编织纹路仍然整齐",
        "unraveled_edge": "边缘严重散线", "soil_coating": "表面粘附细土",
        "indistinct": "表面特征不明显",
    },
    "scale": {
        "palm_fragment": "只剩约一掌宽的残片",
        "two_joining_sheets": "由两片可以拼合的薄片组成",
        "short_roll": "卷起后不足前臂长", "single_corner": "似乎只剩原件的一角",
        "one_hand": "可以单手拿起", "forearm_length": "长度接近一条前臂",
        "several_fragments": "由数块碎片组成", "larger_than_palm": "尺寸略大于手掌",
        "knee_high": "露出地面的部分约齐膝高", "several_paces": "残存部分横跨数步",
        "foundation_only": "只保留了底部轮廓", "large_blocks": "由数块大型构件组成",
        "narrow_band": "在剖面上形成一条窄带", "two_fingers_thick": "厚度约有两指",
        "intermittent_patch": "断续分布在数步范围内",
        "between_layers": "夹在两层颜色不同的土之间", "unknown": "尺寸难以准确判断",
    },
    "mark": {
        "mineral_vein": "浅色矿物脉穿过表面", "soil_in_grooves": "凹槽里积着泥土",
        "thin_moss": "背阴面附着薄苔", "impact_chips": "边角有反复碰撞留下的缺口",
        "force_bend": "一侧留有受力弯曲", "parallel_scratches": "表面有数道平行刮痕",
        "remaining_rivet": "连接处残留铆钉", "fused_soil": "局部附着烧结的土粒",
        "insect_holes": "边缘有细小虫蛀孔", "wax_trace": "角落残留蜡质印记",
        "water_blurred_ink": "数行墨迹被水渍晕开", "missing_fold": "折叠处缺失了一小片",
        "joint_holes": "榫接处仍留有孔洞", "tool_cuts": "表面有工具削切痕",
        "ash_in_cracks": "裂缝中夹着灰土", "dense_growth_rings": "端部可见密集年轮",
        "repair_stitches": "局部留有缝补针脚", "round_stain": "一角有圆形污迹",
        "geometric_pattern": "带有重复的几何纹样", "dark_fold": "折叠处颜色明显较深",
        "no_clear_mark": "没有发现清晰的人工标记",
    },
    "form": {
        "asymmetric": "形状左右并不完全对称",
        "riveted_parts": "几个部件原本似乎由铆钉连接",
        "worn_edges": "边缘有长期使用形成的磨圆",
        "mounting_socket": "底部留有可以固定在其他物体上的接口",
    },
    "arrangement": {
        "aligned": "构件大致沿同一方向排列",
        "hardened_mortar": "石块之间仍可见硬化的填缝材料",
        "wide_base": "底层构件比上层明显更宽",
        "different_orientation": "残存部分与周围后建墙体的方向不同",
    },
    "stratigraphy": {
        "charcoal_and_bone": "其中混有细小炭粒和碎骨屑",
        "uniform_grains": "颗粒大小比上下土层更均匀",
        "thicker_by_wall": "这一层在靠近墙基处明显变厚",
        "pottery_and_metal": "层面上散布着少量陶片和金属屑",
    },
    "script": {
        "narrow_rows": "墨迹以整齐的窄行排列",
        "hurried_hand": "字符大小不一，笔画显得仓促",
        "margin_note": "正文旁有另一种笔迹留下的短注",
        "ruled_columns": "文字被分成数个规则栏目",
    },
    "legibility": {
        "isolated_glyphs": "目前只能辨出零散字符",
        "numbers_and_symbols": "部分数字和重复符号仍然清楚",
        "missing_ends": "首尾已经缺失，中央几行尚可辨认",
        "seal_area_clear": "封印附近的短句保存得相对完整",
    },
    "delivery": {
        "hesitant": "讲述时常出现停顿和自我修正",
        "variant_wording": "不同讲述者会替换其中的少量词句",
        "rhythmic": "句式带有明显的重复和押韵",
        "elder_only": "只有年长居民还能完整复述其中几段",
    },
    "variation": {
        "names_and_numbers": "人名和数字在不同版本中并不一致",
        "divergent_ending": "故事的开头相近，结尾却有两种说法",
        "place_without_date": "讲述者都强调地点，却说不清具体年代",
        "stable_core_unclear_cause": "核心句反复出现，但前后原因并不明确",
    },
}


STATE_PHRASES = {
    "intact": "整体轮廓保存得相对完整",
    "weathered": "暴露和老化已经抹去了一部分细节",
    "ruined": "损坏严重，只能辨认少数局部结构",
    "buried": "遮蔽处保留了较多细节，表面仍带压实泥土",
}


def _tag_map(features: dict) -> dict[str, str]:
    result = {}
    for tag in features.get("tags", []):
        namespace, separator, value = tag.partition(":")
        if separator and namespace not in result:
            result[namespace] = value
    return result


def _phrase(tags: dict[str, str], namespace: str, fallback: str) -> str:
    value = tags.get(namespace, "")
    return PHRASES.get(namespace, {}).get(value, fallback)


def _stable_choice(options: list[str], features: dict) -> str:
    payload = "|".join(features.get("tags", []))
    index = int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)
    return options[index % len(options)]


def describe_evidence(context: dict) -> str:
    """用关键词词组和类型语法拼接玩家可见的观察记录。"""
    evidence_type = context.get("evidence_type", "artifact")
    observed_name = context.get("observed_name", "不明物件")
    state = context.get("state_key", "intact")
    features = context.get("physical_features", {})
    tags = _tag_map(features)

    if evidence_type == "oral":
        delivery = _phrase(tags, "delivery", "讲述中有多处停顿")
        variation = _phrase(tags, "variation", "不同版本之间存在差异")
        return (
            f"你听到一段{observed_name}。{delivery}，而且{variation}。\n\n"
            "这只能确认某种说法仍在当地流传。讲述者没有拿出可以直接核对的原始记录，"
            "目前无法判断哪些部分来自亲历，哪些部分是在反复讲述中增加的。"
        )

    material = _phrase(tags, "material", "不明材料")
    color = _phrase(tags, "color", "颜色难以判断")
    surface = _phrase(tags, "surface", "表面特征不明显")
    scale = _phrase(tags, "scale", "尺寸难以准确判断")
    mark = _phrase(tags, "mark", "没有发现清晰标记")
    condition = STATE_PHRASES.get(state, "保存状态暂时难以判断")

    grammar = {
        "document": [
            f"你把这份{observed_name}放在平整处观察。载体是{color}的{material}，{scale}，{surface}。",
            f"这份{observed_name}{scale}。它以{material}制成，呈{color}，{surface}。",
        ],
        "artifact": [
            f"你仔细查看这件{observed_name}。它由{material}制成，{scale}，呈{color}，{surface}。",
            f"这件{observed_name}{scale}，材质是{material}。它呈{color}，{surface}。",
        ],
        "structure": [
            f"你绕着这处{observed_name}查看。残存部分由{material}构成，{scale}，呈{color}，{surface}。",
            f"这处{observed_name}{scale}。可见构件是{color}的{material}，{surface}。",
        ],
        "environmental": [
            f"你沿裸露剖面查看这处{observed_name}。它{scale}，整体呈{color}，{surface}。",
            f"这处{observed_name}{scale}。它与上下土层颜色不同，呈{color}，{surface}。",
        ],
    }
    opening = _stable_choice(grammar.get(evidence_type, grammar["artifact"]), features)

    detail_parts = [mark, condition]
    if evidence_type == "document":
        detail_parts.extend([
            _phrase(tags, "script", "可以看见少量书写痕迹"),
            _phrase(tags, "legibility", "具体字符难以辨认"),
        ])
        uncertainty = "在完成辨字、比对和释读前，不能确定它记录了什么。"
    elif evidence_type == "artifact":
        detail_parts.append(_phrase(tags, "form", "器形只能辨认一部分"))
        uncertainty = "仅凭外观还不能确定它由谁使用，或为何留在这里。"
    elif evidence_type == "structure":
        detail_parts.append(_phrase(tags, "arrangement", "构件排列并不完整"))
        uncertainty = "现有残存部分不足以确定建筑的年代和具体用途。"
    else:
        detail_parts.append(_phrase(tags, "stratigraphy", "层内成分还需要取样"))
        uncertainty = "形成原因仍需要结合周围地层和其他样本判断。"

    return f"{opening}\n\n{'；'.join(detail_parts)}。{uncertainty}"
