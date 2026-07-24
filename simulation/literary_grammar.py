"""Small semantic atoms and grammar helpers for generated literature."""

from __future__ import annotations

import hashlib


def stable_index(seed: int, key: str, size: int) -> int:
    payload = f"{seed}|{key}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:12], 16) % size


def choose(seed: int, key: str, options: tuple[str, ...]) -> str:
    return options[stable_index(seed, key, len(options))]


WEATHER_STATES = (
    "雨刚停", "北风越过屋顶", "河面起雾", "霜落在路边",
    "暑气仍压着石墙", "远雷越过高地", "融雪流进旧沟", "月光照着空地",
)

MOVEMENT_ACTIONS = (
    "越过", "绕过", "穿过", "离开", "返回", "停在", "沿着", "背向",
)

OBJECT_ACTIONS = (
    "抬起", "放下", "交还", "藏起", "辨认", "擦去", "翻转", "重新钉牢",
)

SPEECH_ACTS = {
    "question": ("追问", "要求解释", "请求核对", "指出矛盾"),
    "deny": ("否认", "拒绝代答", "保留异议", "承认无法确认"),
    "claim": ("陈述", "坚持", "引用旧记", "报告所见"),
    "concede": ("改口", "接受保留空白", "同意复核", "撤回断言"),
}

VOICE_ACTIONS = (
    "记下", "念出", "删去", "重复", "改写", "保留", "校正", "传给后来者",
)

EPIC_BEARINGS = (
    "城门", "渡口", "旧路", "山口", "界石", "桥面", "市场外沿", "高地",
)

EPIC_BURDENS = (
    "粮袋", "工具", "伤者名册", "封存文书", "种子", "药材", "旧旗", "桥索",
)

DRAMATIC_PROPS = (
    "旧名册", "断裂封印", "磨损钥匙", "带水痕的桥石",
    "未署名短笺", "褪色布带", "刻错字的木牌", "缺角印章",
)

LYRIC_LIGHTS = (
    "晨光", "雨前暗云", "迟来的月光", "炉火", "水面反光", "雪后微光",
)

LYRIC_CHANGES = (
    "覆盖", "显出", "带走", "留下", "折回", "磨平", "照亮", "遮住",
)

UNCERTAINTY_ENDINGS = (
    "没有得到同一个答案", "仍留在页边", "没有被后来者补齐",
    "只在异文中保存", "随抄本传到别处", "被新的名称遮住",
)


def sentence(*parts: object, ending: str = "。") -> str:
    text = "".join(str(part) for part in parts if part not in (None, ""))
    return text if text.endswith(("。", "？", "！", "〕")) else text + ending


def stage_direction(*parts: object) -> str:
    return "〔" + sentence(*parts).removesuffix("。") + "。〕"


def dialogue(speaker: str, speech_act: str, proposition: str) -> str:
    return f"{speaker}〔{speech_act}〕：{sentence(proposition)}"


def numbered_name(index: int, unit: str) -> str:
    numerals = (
        "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
        "十一", "十二", "十三", "十四", "十五", "十六",
    )
    label = numerals[index] if index < len(numerals) else str(index + 1)
    return f"第{label}{unit}"
