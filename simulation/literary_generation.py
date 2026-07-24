"""Grounded, deterministic literary composition from historical facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib

from simulation.literary_grammar import (
    DRAMATIC_PROPS,
    EPIC_BEARINGS,
    EPIC_BURDENS,
    LYRIC_CHANGES,
    LYRIC_LIGHTS,
    MOVEMENT_ACTIONS,
    OBJECT_ACTIONS,
    SPEECH_ACTS,
    UNCERTAINTY_ENDINGS,
    VOICE_ACTIONS,
    WEATHER_STATES,
    choose as grammar_choice,
    dialogue,
    numbered_name,
    sentence,
    stage_direction,
)


EVENT_THEMES = {
    "founding": "建城",
    "war": "战乱",
    "raid": "边境冲突",
    "rebellion": "反抗",
    "treaty": "盟约",
    "ruler_change": "继承",
    "disaster": "灾变",
    "relief": "救援",
    "reconstruction": "重建",
    "decline": "衰落",
    "discovery": "技艺",
    "exploration": "远行",
    "construction": "营建",
    "trade": "商路",
    "economic": "生计",
    "population_milestone": "城镇发展",
    "festival": "节庆",
    "marriage": "婚盟",
    "crime": "争讼",
    "duel": "决斗",
    "omen": "天象",
}

ROLE_THEMES = {
    "founder": "建城",
    "ruler": "执政",
    "general": "征战",
    "rebel_leader": "反抗",
    "diplomat": "外交",
    "scholar": "研究",
    "writer": "写作",
    "heir": "继承",
    "priest": "仪式",
}

ROLE_NAMES = {
    "founder": "建城者",
    "ruler": "统治者",
    "general": "军队指挥者",
    "rebel_leader": "反抗领袖",
    "diplomat": "外交使者",
    "scholar": "研究者",
    "writer": "作者",
    "heir": "继承人",
    "priest": "仪式保管人",
}

# Pools contain semantic atoms and short phrases, never complete passages.
STANCE_WORDS = {
    "memorial": ("追记", "留存", "回望", "悼念"),
    "questioning": ("追问", "辨认", "质疑", "复核"),
    "civic": ("编次", "列名", "纪年", "见证"),
}

RECORD_OBJECTS = ("旧卷", "名册", "碑面", "账页", "页边", "残简")
TRACE_OBJECTS = ("水痕", "车辙", "旧钉", "裂纹", "褪色印记", "磨损刻字")
MEMORY_ACTIONS = ("保留", "隐去", "误读", "重述", "校正", "传抄")
TIME_LINKS = ("其后", "后来", "隔年", "多年以后", "再读此事时")
CLAIM_VERBS = ("记作", "称为", "列入", "抄在", "刻进")

FEATURE_IMAGES = {
    "river": ("水痕", "渡口旧桩", "回水湾", "湿润桥石"),
    "lake": ("退水线", "岸边苇根", "浅滩碎石", "静水倒影"),
    "mountain": ("山口回声", "坡上界石", "积雪旧径", "岩壁裂纹"),
    "plains": ("远处车辙", "低伏麦穗", "风中界沟", "空旷地平线"),
    "forest": ("树皮刻痕", "林间旧路", "折断枝条", "苔下界石"),
    "desert": ("沙下车辙", "风蚀路标", "干涸水槽", "裸露石柱"),
    "tundra": ("冻土裂口", "低矮苔痕", "雪中脚印", "结霜界石"),
}

THEME_FAMILIES_BY_EVENT = {
    "founding": ("共同体", "故土变化", "公共责任"),
    "war": ("战争创伤", "归乡", "忠诚", "无名者"),
    "raid": ("边界变化", "恐惧", "归乡", "见证冲突"),
    "rebellion": ("权力合法性", "忠诚", "反抗", "证词冲突"),
    "treaty": ("誓言", "守约", "政治记忆", "边界变化"),
    "ruler_change": ("继承", "权力合法性", "政治宣传", "旧名新称"),
    "disaster": ("灾变生存", "共同体", "失去", "自然与时间"),
    "relief": ("救援责任", "普通人的功绩", "共同体", "债与报偿"),
    "reconstruction": ("重建", "旧物新用", "公共劳动", "故土变化"),
    "decline": ("衰落", "遗忘", "废墟", "离乡"),
    "discovery": ("知识与真相", "技艺传承", "怀疑", "失败记录"),
    "exploration": ("远行", "陌生地名", "归乡", "边界变化"),
    "construction": ("公共劳动", "权力展示", "旧物新用", "共同体"),
    "trade": ("商路", "公平交换", "债与报偿", "异乡来客"),
    "economic": ("生计", "财富分配", "债与报偿", "共同体"),
    "population_milestone": ("城镇发展", "新旧居民", "故土变化"),
    "festival": ("公共记忆", "仪式", "代际传承"),
    "marriage": ("亲属责任", "婚盟", "个人与共同体"),
    "crime": ("证词冲突", "真相", "惩罚", "宽恕"),
    "duel": ("荣誉", "暴力", "见证冲突"),
    "omen": ("信念", "怀疑", "解释权"),
}

DEFAULT_THEME_FAMILIES = ("记忆", "历史缺口", "后来者")

AUTHOR_THEME_FAMILIES = {
    "founder": ("共同体", "故土变化"),
    "ruler": ("权力合法性", "公共责任"),
    "general": ("战争创伤", "忠诚"),
    "rebel_leader": ("反抗", "权力合法性"),
    "diplomat": ("誓言", "边界变化"),
    "scholar": ("知识与真相", "怀疑"),
    "writer": ("记忆", "历史缺口"),
    "heir": ("继承", "亲属责任"),
    "priest": ("信念", "仪式"),
}


def _stable_index(seed: int, key: str, size: int) -> int:
    payload = f"{seed}|{key}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:12], 16) % size


def _choose(seed: int, key: str, options: tuple[str, ...]) -> str:
    return options[_stable_index(seed, key, len(options))]


def event_theme(event_type: str | None) -> str:
    return EVENT_THEMES.get(str(event_type or ""), "往事")


def role_theme(role: str) -> str | None:
    return ROLE_THEMES.get(role)


@dataclass(frozen=True)
class LiteraryWorkPlan:
    genre: str
    stance: str
    narrative_order: str
    narrator: str
    themes: tuple[str, ...]
    primary_theme: str
    secondary_themes: tuple[str, ...]
    structure: tuple[str, ...]
    source_event_ids: tuple[str, ...]
    landscape_names: tuple[str, ...]
    central_image: str
    recurring_action: str
    record_object: str

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in (
                "themes", "secondary_themes", "structure",
                "source_event_ids", "landscape_names"):
            data[key] = list(data[key])
        return data


def _derive_theme_families(seed: int, document_key: str,
                           sources: list[dict],
                           author_roles: tuple[str, ...]) -> tuple[str, ...]:
    scores: dict[str, float] = {}
    for source_index, source in enumerate(sources):
        event_type = str(source.get("event_type", ""))
        importance = float(source.get("importance_score", 0.0))
        for position, theme in enumerate(
                THEME_FAMILIES_BY_EVENT.get(
                    event_type, DEFAULT_THEME_FAMILIES)):
            score = 3.0 - position * 0.35 + importance
            score += _stable_index(
                seed, f"{document_key}|theme:{source_index}:{theme}", 100
            ) / 1000.0
            scores[theme] = scores.get(theme, 0.0) + score
    for role_index, role in enumerate(author_roles):
        for position, theme in enumerate(AUTHOR_THEME_FAMILIES.get(role, ())):
            score = 1.2 - position * 0.2 - role_index * 0.05
            scores[theme] = scores.get(theme, 0.0) + score
    if not scores:
        for index, theme in enumerate(DEFAULT_THEME_FAMILIES):
            scores[theme] = 1.0 - index * 0.1
    ranked = sorted(scores, key=lambda theme: (-scores[theme], theme))
    return tuple(ranked[:3])


def _genre_structure(genre: str) -> tuple[str, ...]:
    return {
        "epic": (
            "departure", "obstacle", "division", "loss",
            "return", "later_judgment",
        ),
        "drama": (
            "conflict", "testimony", "evidence", "reversal", "open_verdict",
        ),
        "lyric_cycle": (
            "landscape", "trace", "historical_event", "time_shift", "refrain",
        ),
        "biography": ("life_record", "public_actions", "later_memory"),
        "chronicle": ("dating", "event_sequence", "editorial_memory"),
    }.get(genre, ("source", "reflection"))


def _make_plan(seed: int, document_key: str, genre: str,
               context: dict) -> LiteraryWorkPlan:
    sources = [
        source for source in context.get("literary_sources", ())
        if isinstance(source, dict)
    ]
    broad_themes = tuple(dict.fromkeys(
        event_theme(source.get("event_type")) for source in sources
    )) or ("往事",)
    theme_families = _derive_theme_families(
        seed, document_key, sources,
        tuple(str(role) for role in context.get("author_roles", ())))
    landscapes = [
        item for item in context.get("landscape_features", ())
        if isinstance(item, dict) and item.get("name")
    ]
    feature = landscapes[
        _stable_index(seed, f"{document_key}|landscape", len(landscapes))
    ] if landscapes else None
    image_options = FEATURE_IMAGES.get(
        feature.get("feature_type") if feature else "", TRACE_OBJECTS)
    stance = (
        "memorial" if any(theme in {"灾变", "战乱", "衰落"}
                          for theme in broad_themes)
        else "questioning" if any(theme in {"继承", "盟约", "反抗"}
                                   for theme in broad_themes)
        else "civic"
    )
    narrator_options = {
        "chronicle": ("后来的编者", "本地抄写者", "无名校读者"),
        "biography": ("传主的后人", "同城见证者", "后来的传记作者"),
        "epic": ("归来的歌者", "沿路传唱者", "城门边的讲述者"),
        "drama": ("节庆编剧", "档案室改编者", "巡回演出者"),
        "lyric_cycle": ("无名歌者", "河岸抄写者", "远行归来者"),
    }.get(genre, ("无名讲述者",))
    return LiteraryWorkPlan(
        genre=genre,
        stance=stance,
        narrative_order=_choose(
            seed, f"{document_key}|order", ("chronological", "retrospective")),
        narrator=_choose(seed, f"{document_key}|narrator", narrator_options),
        themes=broad_themes[:3],
        primary_theme=theme_families[0],
        secondary_themes=theme_families[1:3],
        structure=_genre_structure(genre),
        source_event_ids=tuple(
            str(source.get("event_id", "")) for source in sources
            if source.get("event_id")),
        landscape_names=tuple(str(item["name"]) for item in landscapes[:3]),
        central_image=_choose(
            seed, f"{document_key}|image", tuple(image_options)),
        recurring_action=_choose(
            seed, f"{document_key}|memory", MEMORY_ACTIONS),
        record_object=_choose(
            seed, f"{document_key}|record", RECORD_OBJECTS),
    )


def _passage(kind: str, text: str, unit: str,
             tags: list[str], source_event_id: str | None = None) -> dict:
    result = {
        "kind": kind,
        "text": text,
        "literary_unit": unit,
        "semantic_tags": tags,
    }
    if source_event_id:
        result["source_event_id"] = source_event_id
    return result


def _source_passages(seed: int, document_key: str, source: dict,
                     setting: str, plan: LiteraryWorkPlan,
                     index: int, subject_name: str | None = None) -> list[dict]:
    year = source.get("year", "年份不详")
    title = source.get("title", "一件旧事")
    summary = source.get("summary", title)
    event_id = str(source.get("event_id", "")) or None
    theme = event_theme(source.get("event_type"))
    people = [
        str(name) for name in source.get("person_names", ())
        if isinstance(name, str) and name
    ]
    places = [
        str(name) for name in source.get("participant_names", ())
        if isinstance(name, str) and name
    ]
    claim = _choose(
        seed, f"{document_key}|source:{index}|claim", CLAIM_VERBS)
    transition = _choose(
        seed, f"{document_key}|source:{index}|time", TIME_LINKS)
    locus = "、".join(places[:2]) or setting
    actor = subject_name or (people[0] if people else plan.narrator)
    named_people = "、".join(
        name for name in people if name != actor
    )
    first = (
        f"{year}年，{locus}将“{title}”{claim}{plan.record_object}；"
        f"其中能够核对的记述是：{summary}"
    )
    second_parts = [transition, actor]
    if named_people:
        second_parts.extend(("与", named_people, "一同"))
    second_parts.extend((plan.recurring_action, theme, "留下的", plan.central_image))
    second = "".join(second_parts) + "。"
    return [
        _passage("body", first, "historical_source",
                 ["history", theme], event_id),
        _passage("body", second, "literary_reflection",
                 ["memory", theme], event_id),
    ]


def _source_people(source: dict | None) -> list[str]:
    if not source:
        return []
    return [
        str(name) for name in source.get("person_names", ())
        if isinstance(name, str) and name
    ]


def _historical_anchor(source: dict) -> str:
    year = source.get("year", "年份不详")
    title = source.get("title", "一件旧事")
    summary = source.get("summary", title)
    return sentence(year, "年，", title, "；", summary)


def _compose_epic(seed: int, document_key: str, setting: str,
                  landscape: str, sources: list[dict],
                  plan: LiteraryWorkPlan) -> list[dict]:
    passages = [_passage(
        "body",
        sentence(
            plan.narrator, "从", setting, "的城门起唱，以", landscape,
            "为道路，以", plan.central_image, "为反复出现的标记"),
        "epic_invocation", ["epic", plan.primary_theme],
    )]
    bearings = list(EPIC_BEARINGS)
    anchored_sources: set[str] = set()
    if landscape not in bearings:
        bearings.append(landscape)
    for index, beat in enumerate(plan.structure):
        source = sources[index % len(sources)] if sources else None
        people = _source_people(source)
        actor = people[0] if people else plan.narrator
        bearing = grammar_choice(
            seed, f"{document_key}|epic:{index}|bearing", tuple(bearings))
        burden = grammar_choice(
            seed, f"{document_key}|epic:{index}|burden", EPIC_BURDENS)
        movement = grammar_choice(
            seed, f"{document_key}|epic:{index}|movement", MOVEMENT_ACTIONS)
        weather = grammar_choice(
            seed, f"{document_key}|epic:{index}|weather", WEATHER_STATES)
        if source:
            source_key = str(source.get("event_id") or index)
            if source_key not in anchored_sources:
                anchor_text = _historical_anchor(source)
                anchored_sources.add(source_key)
            else:
                anchor_text = sentence(
                    source.get("year", "年份不详"), "年的",
                    event_theme(source.get("event_type")), "在这一段转为",
                    beat, "的叙事节点")
            passages.append(_passage(
                "body", anchor_text, "historical_source",
                ["history", event_theme(source.get("event_type"))],
                str(source.get("event_id", "")) or None,
            ))
        else:
            passages.append(_passage(
                "body",
                sentence(
                    plan.narrator, "没有找到这一段对应的纪年，只把它作为",
                    plan.primary_theme, "的传唱段落保留下来"),
                "fiction_notice", ["literary_fiction", plan.primary_theme],
            ))

        if beat == "departure":
            text = sentence(
                actor, "从城门", movement, bearing, "，携带", burden,
                "，并把能够确认的姓名交给", plan.record_object)
        elif beat == "obstacle":
            text = sentence(
                weather, "；队伍在", landscape, "附近辨认", plan.central_image,
                "，却不能由这一痕迹推断所有人的去向")
        elif beat == "division":
            other = people[1] if len(people) > 1 else "同行者"
            text = sentence(
                actor, "与", other, "围绕", plan.primary_theme,
                "发生分歧；一方要求继续前行，另一方要求先核对", plan.record_object)
        elif beat == "loss":
            text = sentence(
                burden, "被交还时少了一项标记；", plan.narrator,
                "选择保留缺口，没有替失踪者补写结局")
        elif beat == "return":
            text = sentence(
                actor, movement, "回", setting, "的城门；旧称、新路与",
                plan.central_image, "同时出现在归来者的叙述中")
        else:
            text = sentence(
                "后来者在", plan.record_object, "旁追问", plan.primary_theme,
                "，答案", grammar_choice(
                    seed, f"{document_key}|epic:{index}|uncertain",
                    UNCERTAINTY_ENDINGS))
        passages.append(_passage(
            "body", text, f"epic_{beat}",
            ["epic", beat, plan.primary_theme],
            str(source.get("event_id", "")) if source else None,
        ))
    return passages


def _dramatic_characters(sources: list[dict]) -> list[str]:
    names = list(dict.fromkeys(
        name for source in sources for name in _source_people(source)
    ))
    for role in ("书记", "守门人", "搬运者", "后来者"):
        if role not in names:
            names.append(role)
    return names[:5]


def _compose_drama(seed: int, document_key: str, setting: str,
                   landscape: str, sources: list[dict],
                   plan: LiteraryWorkPlan) -> list[dict]:
    characters = _dramatic_characters(sources)
    anchored_sources: set[str] = set()
    passages = [_passage(
        "body", sentence("人物：", "、".join(characters)),
        "dramatis_personae", ["drama", "characters"],
    )]
    for index, beat in enumerate(plan.structure):
        source = sources[index % len(sources)] if sources else None
        prop = grammar_choice(
            seed, f"{document_key}|drama:{index}|prop", DRAMATIC_PROPS)
        weather = grammar_choice(
            seed, f"{document_key}|drama:{index}|weather", WEATHER_STATES)
        object_action = grammar_choice(
            seed, f"{document_key}|drama:{index}|object", OBJECT_ACTIONS)
        first = characters[index % len(characters)]
        second = characters[(index + 1) % len(characters)]
        act_type = ("question", "claim", "deny", "concede", "question")[index]
        reply_type = ("claim", "deny", "question", "concede", "deny")[index]
        passages.append(_passage(
            "body",
            stage_direction(
                numbered_name(index, "场"), "。", weather, "，地点在",
                landscape if index % 2 else setting, "。", first, object_action, prop),
            f"drama_{beat}_stage", ["drama", beat, "stage"],
            str(source.get("event_id", "")) if source else None,
        ))
        if source:
            source_key = str(source.get("event_id") or index)
            if source_key not in anchored_sources:
                proposition = _historical_anchor(source)
                anchored_sources.add(source_key)
            else:
                proposition = sentence(
                    "关于“", source.get("title", "一件旧事"), "”的发言进入",
                    beat, "阶段，角色仍需区分档案与推断")
            source_id = str(source.get("event_id", "")) or None
        else:
            proposition = sentence(
                "这一场没有对应的档案，角色只能讨论", plan.primary_theme)
            source_id = None
        first_act = grammar_choice(
            seed, f"{document_key}|drama:{index}|act:first",
            SPEECH_ACTS[act_type])
        passages.append(_passage(
            "body", dialogue(first, first_act, proposition),
            f"drama_{beat}_claim", ["drama", beat, act_type], source_id,
        ))
        reply_act = grammar_choice(
            seed, f"{document_key}|drama:{index}|act:reply",
            SPEECH_ACTS[reply_type])
        reply = sentence(
            plan.record_object, "能够保存文字，却不能替所有人决定",
            plan.primary_theme, "的含义")
        passages.append(_passage(
            "body", dialogue(second, reply_act, reply),
            f"drama_{beat}_reply", ["drama", beat, reply_type], source_id,
        ))
    return passages


def _compose_lyric_cycle(seed: int, document_key: str, setting: str,
                         landscape: str, sources: list[dict],
                         plan: LiteraryWorkPlan) -> list[dict]:
    passages = [_passage(
        "body",
        sentence(
            plan.narrator, "把", landscape, "、", plan.central_image,
            "和", plan.record_object, "编成十二首相互回应的短章"),
        "lyric_invocation", ["lyric", plan.primary_theme],
    )]
    anchored_sources: set[str] = set()
    for index in range(12):
        source = sources[index % len(sources)] if sources else None
        light = grammar_choice(
            seed, f"{document_key}|lyric:{index}|light", LYRIC_LIGHTS)
        change = grammar_choice(
            seed, f"{document_key}|lyric:{index}|change", LYRIC_CHANGES)
        voice = grammar_choice(
            seed, f"{document_key}|lyric:{index}|voice", VOICE_ACTIONS)
        locus = landscape if index % 3 == 0 else setting
        parts = [
            numbered_name(index, "首"), "：", light, "在", locus,
            change, plan.central_image, "；", plan.narrator, voice,
            plan.primary_theme,
        ]
        source_id = None
        if source:
            source_key = str(source.get("event_id") or index)
            if source_key not in anchored_sources:
                parts.extend(("。它回应", _historical_anchor(source)))
                anchored_sources.add(source_key)
            else:
                parts.extend((
                    "。它再次触及", source.get("year", "年份不详"), "年的",
                    event_theme(source.get("event_type")),
                    "，但改变了意象与叙述位置",
                ))
            source_id = str(source.get("event_id", "")) or None
        else:
            parts.append("，但没有把传唱内容写成历史事实")
        passages.append(_passage(
            "body", sentence(*parts), "lyric_stanza",
            ["lyric", plan.primary_theme, f"stanza:{index + 1}"], source_id,
        ))
    return passages


def compose_grounded_literature(
        seed: int, document_key: str, work_title: str, author: str,
        genre: str, context: dict | None = None,
) -> tuple[list[dict], dict]:
    """Compose current grounded genres without selecting complete sentences."""
    context = context or {}
    plan = _make_plan(seed, document_key, genre, context)
    setting = str(context.get("setting_name", "这座城镇"))
    creation_year = context.get("creation_year", "年份不详")
    sources = [
        source for source in context.get("literary_sources", ())
        if isinstance(source, dict)
    ]
    landscape = plan.landscape_names[0] if plan.landscape_names else setting
    passages = [
        _passage("heading", f"《{work_title}》", "title", ["title"]),
        _passage("attribution", f"作者：{author}。", "attribution", ["author"]),
    ]

    if genre == "epic":
        passages.extend(_compose_epic(
            seed, document_key, setting, landscape, sources, plan))
    elif genre == "drama":
        passages.extend(_compose_drama(
            seed, document_key, setting, landscape, sources, plan))
    elif genre == "lyric_cycle":
        passages.extend(_compose_lyric_cycle(
            seed, document_key, setting, landscape, sources, plan))
    elif genre == "biography":
        subject = str(context.get(
            "biography_subject_name", "传主姓名不详"))
        birth = context.get("biography_subject_birth_year")
        death = context.get("biography_subject_death_year")
        life = (
            f"生于{birth}年，卒于{death}年" if birth is not None and death is not None
            else f"生于{birth}年，成书时仍在世" if birth is not None
            else "生卒年份未能确认"
        )
        roles = [
            ROLE_NAMES.get(role, str(role))
            for role in context.get("biography_subject_roles", ())
        ]
        role_text = "、".join(roles) or "身份记录不完整"
        passages.append(_passage(
            "body",
            f"{creation_year}年，{author}在{setting}整理{subject}的旧事；"
            f"以{landscape}附近所见的{plan.central_image}作为全篇反复出现的记号。",
            "prologue", ["composition", plan.stance],
        ))
        passages.append(_passage(
            "body", f"{subject}{life}；现存名册称其为{role_text}。",
            "life_record", ["person", "identity"],
        ))
        for index, source in enumerate(sources):
            passages.extend(_source_passages(
                seed, document_key, source, setting, plan, index, subject))
        if not sources:
            passages.append(_passage(
                "body", f"关于{subject}的事件记录没有保存下来，"
                f"{plan.narrator}只在{plan.record_object}发现其姓名。",
                "lacuna_notice", ["missing_history", "person"],
            ))
    else:
        passages.append(_passage(
            "body",
            f"{creation_year}年，{author}在{setting}编定此书；"
            f"篇章以{landscape}和{plan.central_image}连接不同年代。",
            "prologue", ["composition", plan.stance],
        ))
        ordered_sources = list(sources)
        if plan.narrative_order == "retrospective":
            ordered_sources.reverse()
        for index, source in enumerate(ordered_sources):
            passages.extend(_source_passages(
                seed, document_key, source, setting, plan, index))
        if not sources:
            passages.append(_passage(
                "body", f"{setting}早年的{plan.record_object}已经散失；"
                f"现存文字只能{plan.recurring_action}{plan.central_image}。",
                "lacuna_notice", ["missing_history", "place"],
            ))

    stance_word = _choose(
        seed, f"{document_key}|stance-word", STANCE_WORDS[plan.stance])
    passages.append(_passage(
        "closing",
        f"卷末以“{landscape}仍在，{plan.record_object}未必完整”收束；"
        f"{plan.narrator}将此篇视为一次{stance_word}。",
        "closing", ["closure", plan.stance],
    ))
    return passages, plan.to_dict()
