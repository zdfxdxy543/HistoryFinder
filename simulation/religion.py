"""Deterministic religious traditions and settlement-level religious state."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


SACRED_FOCI = (
    ("守火", "未熄之火", "火焰"),
    ("长河", "循环之水", "水波"),
    ("晨光", "门槛上的晨光", "日轮"),
    ("群山", "保存姓名的山石", "山形"),
    ("古树", "连接生者与逝者的古树", "双枝"),
    ("星轮", "标记季节的群星", "星点"),
    ("归土", "接纳遗骨与种子的土地", "层土"),
    ("静水", "映照誓言的静水", "水盂"),
)
NAME_SUFFIXES = (
    "之誓", "礼法", "旧仪", "传承", "圣约", "祭仪",
)

DOCTRINE_RELATIONS = (
    "见证", "维系", "衡量", "提醒人们履行", "把世代相隔的记忆连入",
)
COMMUNAL_DUTIES = (
    "守护共同水源", "保存逝者姓名", "接待远行者", "公平分配谷物",
    "公开见证誓约", "修补前人留下的公共建筑", "照料无亲属的死者",
)
SYMBOL_COUNTS = ("一道", "三道", "四重", "七点", "成对的", "交叠的")
SYMBOL_FRAMES = ("环绕门形", "置于水盂之上", "夹在双枝之间", "围成开口圆环")
RITUAL_TIMES = (
    "日出前", "晨光越过门槛时", "正午影子最短时", "日落后",
    "新月前夜", "季末集市散场后", "第一场春雨后",
)
OPENING_ACTIONS = (
    "点亮公共灯盏", "清洗门槛", "展开姓名名录", "绕祭石巡行一周",
    "把计日石排成圆环", "打开朝向来路的门扉",
)
OFFERINGS = ("清水", "新谷", "灯油", "盐与干果", "编结草绳", "刻名小石")
RESPONSES = (
    "逐人报出自己的姓名", "重复领诵者的末句", "交换手中的计日石",
    "按街区依次献上供物", "为不在场者留出一次回应", "共同静默一刻",
)
CLOSING_ACTIONS = (
    "把余水倒回公共井旁", "将供物分给旅人与贫者", "记录实际日期与见证人",
    "熄去一半灯盏并保留守夜灯", "沿原路反向走回城门",
)
CALENDAR_ANCHORS = (
    "新月", "满月", "昼夜等长日", "第一场春雨", "收获后的首个集市日",
    "河水开始回落之日", "山顶积雪消失之日",
)
OFFICIANTS = ("守灯者", "记名人", "献水人", "年长见证者", "经卷保管人")
PROTECTED_THINGS = (
    "公共水源", "墓石上的姓名", "供旅人通行的城门", "旧誓词的可辨部分",
    "无人认领的遗骨", "仪式中记录的异议",
)
PROHIBITED_ACTIONS = ("污染", "抹去", "封闭", "私自占有", "焚毁", "倒写日期以掩盖")
REPAIRS = (
    "当众修复并留下姓名", "补献相同数量的供物", "请两名无亲属关系者复核",
    "在下一次集会中公开说明经过",
)

PROFILE_LABELS = {
    "sacred_focus": "神圣对象",
    "ethical_duty": "共同义务",
    "calendar_anchor": "祭历基准",
    "offering": "供物",
    "officiant": "主持者",
    "congregation_response": "列席回应",
    "ritual_steps": "仪式次序",
    "sacred_symbol": "公共符号",
    "taboo": "禁忌",
}

SACRED_LANDSCAPE_BY_BIOME = {
    "river": "river", "river_valley": "river", "lake": "river",
    "mountain": "mountain", "highland": "mountain",
    "forest": "forest", "desert": "spring", "scrubland": "spring",
    "tundra": "stone", "grassland": "open_sky", "plains": "open_sky",
}


def _stable_int(*parts: str) -> int:
    payload = "|".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def changed_profile_dimensions(parent: dict, reformed: dict) -> list[str]:
    """Return semantic fields changed by a reform, in display order."""
    return [
        field for field in PROFILE_LABELS
        if parent.get(field) != reformed.get(field)
    ]


def describe_profile_change(field: str, before, after) -> str:
    label = PROFILE_LABELS.get(field, field)
    if field == "ritual_steps":
        before = "，再".join(before or ["次序未记"])
        after = "，再".join(after or ["次序未记"])
    return f"{label}由“{before}”改为“{after}”"


def compose_festival_description(year: int, settlement_name: str,
                                 profile: dict) -> str:
    steps = profile.get("ritual_steps") or [profile.get(
        "primary_ritual", "举行公共祭仪")]
    sequence = "，随后".join(steps[:3])
    return (
        f"{year}年，{settlement_name}以{profile.get('calendar_anchor', '本地历法')}"
        f"确定{profile.get('name', '当地传统')}的集会日期。"
        f"仪式由{profile.get('officiant', '仪式保管人')}主持，{sequence}；"
        f"列席者以“{profile.get('congregation_response', '共同回应')}”作答。"
    )


def compose_omen_interpretation(profile: dict, phenomenon: str) -> str:
    return (
        f"{profile.get('name', '当地传统')}的{profile.get('officiant', '记录者')}"
        f"把{phenomenon}与{profile.get('sacred_focus', '共同誓约')}相联系，"
        f"并要求列席者{profile.get('ethical_duty', '保存见证')}；"
        "该解释在记录中与观测经过分列。"
    )


def compose_reform_description(year: int, settlement_name: str,
                               parent: dict, reformed: dict,
                               reason: str) -> tuple[str, list[str]]:
    changed = changed_profile_dimensions(parent, reformed)
    clauses = [
        describe_profile_change(field, parent.get(field), reformed.get(field))
        for field in changed[:3]
    ]
    return (
        f"{year}年，{settlement_name}的仪式保管人以{reason}为由，"
        f"将{parent.get('name', '旧有礼法')}整理为"
        f"{reformed.get('name', '新仪传统')}。"
        + "；".join(clauses)
        + "。异议者要求把旧本与新本并列保存。"
    ), changed


def compose_conflict_description(year: int, settlement_name: str,
                                 dominant: dict, minority: dict) -> str:
    return (
        f"{year}年，{settlement_name}对公共祭仪的使用发生争执。"
        f"{dominant.get('name', '官方传统')}要求由"
        f"{dominant.get('officiant', '指定主持者')}按"
        f"{dominant.get('calendar_anchor', '官方祭历')}主持集会，"
        f"而{minority.get('name', '另一传统')}仍使用"
        f"{minority.get('sacred_symbol', '旧符号')}并献上"
        f"{minority.get('offering', '旧有供物')}。禁令与地方传唱对此各有说法。"
    )


@dataclass
class ReligionTradition:
    id: str
    name: str
    founded_year: int
    origin_settlement_id: str
    parent_id: str | None = None
    doctrine: str = ""
    sacred_symbol: str = ""
    primary_ritual: str = ""
    taboo: str = ""
    sacred_landscape: str = "open_sky"
    reform_reason: str = ""
    sacred_focus: str = ""
    ethical_duty: str = ""
    calendar_anchor: str = ""
    offering: str = ""
    officiant: str = ""
    congregation_response: str = ""
    ritual_steps: tuple[str, ...] = ()
    schema_version: int = 1

    def to_dict(self) -> dict:
        data = dict(self.__dict__)
        data["ritual_steps"] = list(self.ritual_steps)
        return data

    def text_profile(self) -> dict:
        return {
            "name": self.name,
            "doctrine": self.doctrine,
            "sacred_symbol": self.sacred_symbol,
            "primary_ritual": self.primary_ritual,
            "taboo": self.taboo,
            "sacred_focus": self.sacred_focus,
            "ethical_duty": self.ethical_duty,
            "calendar_anchor": self.calendar_anchor,
            "offering": self.offering,
            "officiant": self.officiant,
            "congregation_response": self.congregation_response,
            "ritual_steps": list(self.ritual_steps),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReligionTradition":
        return cls(
            id=data["id"],
            name=data["name"],
            founded_year=int(data["founded_year"]),
            origin_settlement_id=data["origin_settlement_id"],
            parent_id=data.get("parent_id"),
            doctrine=data.get("doctrine", ""),
            sacred_symbol=data.get("sacred_symbol", ""),
            primary_ritual=data.get("primary_ritual", ""),
            taboo=data.get("taboo", ""),
            sacred_landscape=data.get("sacred_landscape", "open_sky"),
            reform_reason=data.get("reform_reason", ""),
            sacred_focus=data.get("sacred_focus", data.get("doctrine", "共同誓约")),
            ethical_duty=data.get("ethical_duty", "保存共同体的记忆"),
            calendar_anchor=data.get("calendar_anchor", "新月"),
            offering=data.get("offering", "清水"),
            officiant=data.get("officiant", "仪式保管人"),
            congregation_response=data.get(
                "congregation_response", "重复领诵者的末句"),
            ritual_steps=tuple(data.get("ritual_steps", ())),
            schema_version=int(data.get("schema_version", 1)),
        )


class ReligionManager:
    def __init__(self, seed: int,
                 traditions: dict[str, ReligionTradition] | None = None):
        self.seed = seed
        self.traditions = traditions if traditions is not None else {}
        self.counter = max((
            int(item.id.rsplit("_", 1)[-1])
            for item in self.traditions.values()
            if item.id.rsplit("_", 1)[-1].isdigit()
        ), default=0)

    def create_origin(self, settlement, year: int) -> ReligionTradition:
        key = f"{self.seed}|{settlement.id}|origin"
        return self._create(
            settlement.id, settlement.biome, year, key, parent=None,
            reform_reason="",
        )

    def create_reform(self, parent: ReligionTradition, settlement,
                      year: int, reason: str) -> ReligionTradition:
        key = f"{self.seed}|{parent.id}|{settlement.id}|{year}|{reason}"
        tradition = self._create(
            settlement.id, settlement.biome, year, key,
            parent=parent, reform_reason=reason,
        )
        tradition.name = self._unique_name(
            f"新{parent.name.removesuffix('传承').removesuffix('礼法')}传承",
            key,
        )
        return tradition

    def _create(self, settlement_id: str, biome: str, year: int, key: str,
                parent: ReligionTradition | None,
                reform_reason: str) -> ReligionTradition:
        self.counter += 1
        tradition_id = f"religion_{self.counter:04d}"
        value = _stable_int(key)
        focus = SACRED_FOCI[value % len(SACRED_FOCI)]
        duty = COMMUNAL_DUTIES[(value // 13) % len(COMMUNAL_DUTIES)]
        relation = DOCTRINE_RELATIONS[(value // 17) % len(DOCTRINE_RELATIONS)]
        ritual_time = RITUAL_TIMES[(value // 19) % len(RITUAL_TIMES)]
        opening = OPENING_ACTIONS[(value // 23) % len(OPENING_ACTIONS)]
        offering = OFFERINGS[(value // 29) % len(OFFERINGS)]
        response = RESPONSES[(value // 31) % len(RESPONSES)]
        closing = CLOSING_ACTIONS[(value // 37) % len(CLOSING_ACTIONS)]
        calendar_anchor = CALENDAR_ANCHORS[
            (value // 41) % len(CALENDAR_ANCHORS)]
        officiant = OFFICIANTS[(value // 43) % len(OFFICIANTS)]
        protected = PROTECTED_THINGS[(value // 47) % len(PROTECTED_THINGS)]
        prohibited = PROHIBITED_ACTIONS[(value // 53) % len(PROHIBITED_ACTIONS)]
        repair = REPAIRS[(value // 59) % len(REPAIRS)]
        if parent is None:
            proposed = (
                focus[0]
                + NAME_SUFFIXES[(value // 11) % len(NAME_SUFFIXES)])
        else:
            proposed = parent.name
        tradition = ReligionTradition(
            id=tradition_id,
            name=self._unique_name(proposed, key),
            founded_year=year,
            origin_settlement_id=settlement_id,
            parent_id=parent.id if parent else None,
            doctrine=(parent.doctrine if parent and value % 3 else
                      f"{focus[1]}被认为能够{relation}{duty}"),
            sacred_symbol=(parent.sacred_symbol if parent and value % 2 else
                           f"{SYMBOL_COUNTS[(value // 7) % len(SYMBOL_COUNTS)]}"
                           f"{focus[2]}{SYMBOL_FRAMES[(value // 61) % len(SYMBOL_FRAMES)]}"),
            primary_ritual=(parent.primary_ritual if parent and value % 5 else
                            f"{ritual_time}{opening}"),
            taboo=(parent.taboo if parent and value % 4 else
                   f"不得{prohibited}{protected}；违者须{repair}"),
            sacred_landscape=SACRED_LANDSCAPE_BY_BIOME.get(
                biome, "open_sky"),
            reform_reason=reform_reason,
            sacred_focus=(parent.sacred_focus if parent and value % 3
                          else focus[1]),
            ethical_duty=(parent.ethical_duty if parent and value % 3
                          else duty),
            calendar_anchor=(parent.calendar_anchor if parent and value % 5
                             else calendar_anchor),
            offering=(parent.offering if parent and value % 5 else offering),
            officiant=(parent.officiant if parent and value % 7 else officiant),
            congregation_response=(
                parent.congregation_response if parent and value % 5
                else response),
            ritual_steps=(
                parent.ritual_steps if parent and value % 5 else
                (f"由{officiant}{opening}", f"参与者献上{offering}",
                 f"列席者{response}", closing)),
        )
        if parent is not None and not changed_profile_dimensions(
                parent.text_profile(), tradition.text_profile()):
            responses = list(RESPONSES)
            current = responses.index(parent.congregation_response) \
                if parent.congregation_response in responses else 0
            tradition.congregation_response = responses[(current + 1) % len(responses)]
            steps = list(tradition.ritual_steps or parent.ritual_steps)
            if steps:
                response_step = f"列席者{tradition.congregation_response}"
                steps[min(2, len(steps) - 1)] = response_step
                tradition.ritual_steps = tuple(steps)
        self.traditions[tradition.id] = tradition
        return tradition

    def _unique_name(self, proposed: str, key: str) -> str:
        used = {item.name for item in self.traditions.values()}
        if proposed not in used:
            return proposed
        qualifiers = ("东仪", "西仪", "河源", "山门", "古礼", "新约")
        start = _stable_int(key, "qualifier") % len(qualifiers)
        for offset in range(len(qualifiers)):
            candidate = f"{qualifiers[(start + offset) % len(qualifiers)]}{proposed}"
            if candidate not in used:
                return candidate
        return f"{proposed}第{self.counter}支"


def primary_religion(settlement, traditions: dict[str, ReligionTradition]
                     ) -> ReligionTradition | None:
    religion_id = settlement.official_religion_id
    if religion_id not in traditions and settlement.religious_presence:
        religion_id = max(
            settlement.religious_presence,
            key=lambda key: (settlement.religious_presence[key], key),
        )
    return traditions.get(religion_id)
