"""Deterministic lightweight library catalogs with lazy book text."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field


BOOKS_PER_SHELF_TARGET = 48
MAX_LIBRARY_SHELVES = 12
BOOK_TEXT_PLAN_VERSION = 1
BOOK_CONTENT_VERSION = 1
BOOK_DAMAGE_VERSION = 1

DAMAGE_LABELS = {
    "faded_ink": "字迹褪色",
    "water_blur": "水渍漫漶",
    "insect_holes": "虫蛀缺字",
    "torn_edge": "页缘残缺",
    "stuck_pages": "书页粘连",
    "missing_leaves": "缺叶",
}

GENRES = {
    "history": "历史",
    "literature": "文学",
    "medicine": "医学",
    "law": "律法",
    "geography": "地理",
    "theology": "宗教",
    "agriculture": "农学",
    "astronomy": "天文",
    "craft": "工艺",
    "philosophy": "哲学",
}

_TITLE_PARTS = {
    "history": (("诸城", "王朝", "边地", "旧都", "河谷"), ("纪年", "兴衰录", "人物志", "战事考", "旧闻集")),
    "literature": (("长夜", "归舟", "群山", "秋庭", "远行"), ("诗抄", "歌集", "故事集", "剧稿", "寓言")),
    "medicine": (("热病", "草药", "创伤", "脉息", "饮食"), ("辨证", "方略", "疗法", "札记", "图解")),
    "law": (("市民", "田亩", "商旅", "婚契", "刑名"), ("律例", "判例集", "释义", "条议", "问答")),
    "geography": (("北方", "群河", "沿海", "荒原", "诸山"), ("地志", "行程录", "水道考", "舆图解", "风物记")),
    "theology": (("晨祷", "诸圣", "祭仪", "神迹", "戒律"), ("经注", "仪轨", "讲章", "问答", "赞歌集")),
    "agriculture": (("谷种", "果木", "水渠", "土性", "牧养"), ("时令", "栽培法", "经验录", "图说", "要略")),
    "astronomy": (("星位", "月行", "日影", "节气", "天象"), ("观测录", "推步法", "图表", "校记", "要义")),
    "craft": (("木作", "冶炼", "陶器", "桥梁", "织染"), ("工法", "尺度录", "图谱", "匠人札记", "材料考")),
    "philosophy": (("自然", "知识", "德性", "秩序", "因果"), ("论集", "辩难", "讲义", "沉思录", "原理论")),
}

_AUTHOR_ROLES = {
    "history": "编年者", "literature": "诗人", "medicine": "医师",
    "law": "书记官", "geography": "旅行者", "theology": "经师",
    "agriculture": "农师", "astronomy": "观星者", "craft": "工匠",
    "philosophy": "学者",
}

_FORMS = {
    "history": ("编年史", "人物列传", "地方志", "史论"),
    "literature": ("故事集", "组诗", "寓言集", "戏剧稿"),
    "medicine": ("医案汇编", "诊疗手册", "药物图录", "讲学笔记"),
    "law": ("律例释义", "判例集", "官吏问答", "条文汇编"),
    "geography": ("行程录", "地方志", "水陆图说", "旅行指南"),
    "theology": ("经文注疏", "仪式手册", "讲章集", "神学问答"),
    "agriculture": ("农事月令", "栽培手册", "田间经验录", "物产图说"),
    "astronomy": ("观测日志", "星表解说", "推步手册", "天象问答"),
    "craft": ("工艺图谱", "作坊手册", "材料试验录", "匠人讲义"),
    "philosophy": ("论证集", "师生问答", "概念释义", "辩难录"),
}

_AUDIENCES = {
    "history": ("地方官员", "抄写员", "普通读者"),
    "literature": ("市民读者", "行旅艺人", "贵族听众"),
    "medicine": ("医师学徒", "乡间治疗者", "药材商人"),
    "law": ("书记官", "地方裁判者", "契约见证人"),
    "geography": ("商旅", "测绘者", "远行者"),
    "theology": ("祭司学徒", "礼仪主持者", "普通信众"),
    "agriculture": ("农户", "庄园管事", "水利人员"),
    "astronomy": ("观测学徒", "历法官", "航行者"),
    "craft": ("作坊学徒", "熟练工匠", "工程管事"),
    "philosophy": ("学者", "讲堂学生", "公共辩论者"),
}

_OUTLINES = {
    "history": ("编写缘起", "年代与证词", "关键事件", "人物评价", "异说辨析", "年表附录"),
    "literature": ("献辞", "开篇场景", "人物与冲突", "转折", "结局", "抄本后记"),
    "medicine": ("适用范围", "症状辨识", "材料与剂量", "治疗步骤", "病例与失败", "禁忌索引"),
    "law": ("适用对象", "核心条文", "办理程序", "判例", "争议意见", "修订附记"),
    "geography": ("行程说明", "地貌与水源", "聚落与物产", "道路里程", "风险与季节", "地名索引"),
    "theology": ("经义提要", "核心教义", "仪式次序", "象征释义", "教内争论", "赞词与历日"),
    "agriculture": ("土地与季节", "种植准备", "灌溉与养护", "病害处置", "收获比较", "农时表"),
    "astronomy": ("观测器具", "记录方法", "周期计算", "异常天象", "误差争论", "星表附录"),
    "craft": ("材料选择", "工具与尺度", "制作工序", "接合与加固", "故障修补", "尺寸图表"),
    "philosophy": ("问题界定", "基本命题", "论证", "反例", "异议答辩", "未决问题"),
}

_VOICES = {
    "precise": "作者反复标出范围和例外，避免把局部经验写成普遍定律。",
    "didactic": "行文采用训诫口吻，要求读者按次序学习而不要跳过基础。",
    "skeptical": "作者对流行说法保持怀疑，并把不能复核的部分明确搁置。",
    "confident": "作者语气笃定，但在少数关键处没有交代材料来源。",
    "plain": "文字简短直接，显然是为实际使用而不是炫示学问。",
    "ornate": "行文充满比喻和对偶，事实说明常被修辞包裹。",
}

_STANCES = {
    "traditional": "全书倾向维护旧有解释，把改变视为需要谨慎证明的例外。",
    "reformist": "作者主张修订旧法，并用当地经验证明沿袭并非总是可靠。",
    "balanced": "作者把相反意见并列，较少替读者作出最终判断。",
    "pragmatic": "判断标准主要是能否在实际工作中重复取得结果。",
}

_SOURCE_NOTES = {
    "eyewitness": "书中声称主要材料来自作者亲历，但亲历范围只限于一地。",
    "interviews": "材料来自多位受访者，姓名和身份并非每一处都有记录。",
    "older_books": "作者大量摘录旧书，并偶尔指出不同抄本之间的差异。",
    "official_records": "主要依据官署记录，普通人的经历只在少数段落中出现。",
    "oral_reports": "不少内容来自口头传闻，作者尝试按重复出现的细节排序。",
}

_SECTION_TEMPLATES = {
    "history": (
        "本书在{place}写成，作者把{event_year}年的“{event}”视为划分前后时期的界标，并说明纪年可能受后世改写。",
        "编者比较官署记录、旧书与口述名单；围绕{primary}的记载有两套次序，只有共同出现的人名被列入正文。",
        "叙事沿{feature}展开，记录道路、粮食和传令速度如何改变事件结果，而不是只归因于统治者的意志。",
        "人物章节分别列出支持者与反对者的评价，并提醒{audience}不要把胜者留下的称号当作中立描述。",
        "关于{secondary}，一派认为它延续旧制，另一派则称其为突变；作者承认现有材料不能彻底裁决。",
        "附录按年份列出地名、职衔和版本差异，其中缺失年份保留空栏，没有用推测填补。",
    ),
    "literature": (
        "献辞把{feature}称作记忆的边界，并把全书献给在{place}等待远行者归来的无名读者。",
        "开篇写{primary}笼罩街道，主人公携带一封没有署名的短札进入城门；叙述刻意隐去来处。",
        "人物围绕{event}产生冲突：一人坚持公开旧事，另一人担心公开会伤害仍活着的人。",
        "故事在{secondary}意象再次出现时转折，先前被视为证据的物件被发现只是抄本中的修辞。",
        "结局没有宣布谁完全正确，只写众人在{feature}旁分别保存了不同版本的回忆。",
        "后记说明此稿曾为{audience}朗读，若干重复句可能来自表演者而非最初作者。",
    ),
    "medicine": (
        "本书只讨论{place}常见的{primary}相关病症，并声明孕妇、幼儿和长期虚弱者不应直接照用。",
        "诊断先观察冷热、脉息、饮水和疼痛位置，再把持续时间写入表格；单一症状不足以定病。",
        "材料章节比较本地产物与来自{trade_partner}的替代药材，要求记录重量、煎煮时间和采集季节。",
        "治疗按清洁、少量试用、复查反应和调整剂量四步进行，出现呼吸困难时必须立即停止。",
        "病例包括一次缓解和一次失败；失败者同时经历“{event}”，作者因此拒绝把结果完全归于药方。",
        "禁忌索引列出相冲药材、错误剂量和无法判断的症状，末页注明这不是保证治愈的秘方。",
    ),
    "law": (
        "条文适用于{place}登记的居民、商旅与契约见证人，但对军队和宗教领地另有未收录的规则。",
        "核心条文围绕{primary}规定申诉期限、证人数量和文书格式；缺少印记不会自动证明内容虚假。",
        "办理程序要求书记官分别记录请求、反对意见和裁决理由，禁止先写结论再补证词。",
        "判例取自“{event}”之后的争议，裁判者因两份副本措辞不同而没有采用最严厉处罚。",
        "异议者认为{secondary}条款偏向有能力保存文书的人，编者把这项批评保留在正文旁。",
        "修订附记列出废止、仍有效和地方惯例三栏，提醒{audience}查明年份后再引用。",
    ),
    "geography": (
        "行程从{place}出发，以步行日程而非直线距离计量，并说明雨季会使同一路段耗时增加。",
        "地貌章节描述{feature}附近的坡度、水源和可辨标志；{primary}只在天气清晰时适合作为方向参照。",
        "沿途聚落按饮水、住宿和物产分类，来自{trade_partner}的商人补充了几处季节性集市。",
        "里程采用实走次数的中位数，作者删除了一次因迷路而异常延长的记录，但在页边保留说明。",
        "风险表把洪水、落石、盗匪和迷雾分季节排列，并以“{event}”作为道路中断的实例。",
        "索引同时保存旧地名与新地名；无法确认是否同一地点的名称没有被强行合并。",
    ),
    "theology": (
        "提要称{religion}的教导应在{place}的日常义务中实践，而不能只在节庆时背诵。",
        "核心教义借{primary}解释秩序与责任，并承认象征本身不能替代行为。",
        "仪式章节依次记录主持者、供物、回应和结束动作，遗漏步骤时应暂停而非秘密补做。",
        "象征释义把{feature}与{secondary}联系起来，但注明其他地区存在不同解释。",
        "争论章节收录传统派与改革派对“{event}”的相反理解，编者没有删除败方的答辩。",
        "末卷列出赞词、纪念日和禁忌，同时提醒{audience}地方历法可能相差一日。",
    ),
    "agriculture": (
        "作者先记录{place}的土色、降水与风向，再讨论{primary}，反对不看土地便照搬播种日期。",
        "整地步骤包括清沟、试水和小片播种；种子先分批测试，不把全部储备押在一次判断上。",
        "灌溉章节依据{feature}的季节变化安排轮次，并比较来自{trade_partner}的水渠做法。",
        "病害处置要求先隔离受损植株，再区分虫害、积水和土壤贫瘠，三者不能使用同一办法。",
        "收获表比较“{event}”前后的产量，但作者指出劳力和气候同时变化，不能只归因于新工具。",
        "农时表以旬为单位，附有{secondary}的失败记录，供下一年修正而不是作为固定吉日。",
    ),
    "astronomy": (
        "观测器具包括直杆、刻度绳和水平水盘；作者要求在{place}固定位置重复测量{primary}。",
        "日志同时记录日期、云量、地平线遮挡和观测者，缺少任一项的数据不进入主表。",
        "周期计算以多次间隔的平均值为基础，并展示一次计算错误如何改变对{secondary}的预测。",
        "异常天象章节记录“{event}”附近的报告，但没有把地面事件解释为天象造成。",
        "争论集中在{feature}遮挡与历法换算造成的误差；不同观测点的数据被分栏保存。",
        "附表给出星位、影长和季节标记，提醒{audience}不要用一年的记录推定永久周期。",
    ),
    "craft": (
        "材料章节比较{place}常见木材、金属与绳索，说明{primary}应先做小样再用于承重部位。",
        "工具按测量、切削、钻孔和固定排列，每次开工前都要检查尺度是否因磨损而缩短。",
        "工序从放样开始，经过粗制、试装和精修；来自{trade_partner}的做法被列作替代方案。",
        "接合章节讨论{secondary}在干燥与潮湿环境中的变化，并用{feature}附近工程说明维护周期。",
        "故障记录包含开裂、松动和偏斜；“{event}”后的修补证明加厚构件并不总能解决基础问题。",
        "尺寸表保留允许误差、材料批次和检验人三栏，要求{audience}记录失败品而非只陈列成品。",
    ),
    "philosophy": (
        "作者从“我们如何知道{primary}”开始，区分名称、感觉、记忆与可重复的判断。",
        "基本命题认为秩序需要理由而非权威称号，并以{place}的日常争议说明概念边界。",
        "论证逐步列出前提、中间推论和结论；若关于“{event}”的前提不成立，结论也必须撤回。",
        "反例取自{feature}附近不同观察者对{secondary}的描述，表明相同词语未必指向相同经验。",
        "异议者批评作者过度依赖书面定义，作者回应说口述传统同样需要说明传递过程。",
        "末章把仍无法回答的问题留给{audience}，没有把暂时缺少反例当成已经证明。",
    ),
}


def _stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


@dataclass
class LibraryBook:
    id: str
    collection_id: str
    settlement_id: str
    shelf_id: str
    catalog_number: int
    title: str
    genre: str
    author_name: str
    language_code: str
    created_year: int
    origin_name: str
    condition: str
    text_seed: int
    text_plan: dict = field(default_factory=dict)
    written_content: dict = field(default_factory=dict)
    damage_state: dict = field(default_factory=dict)
    schema_version: int = 2

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict) -> "LibraryBook":
        return cls(
            id=str(data["id"]),
            collection_id=str(data["collection_id"]),
            settlement_id=str(data["settlement_id"]),
            shelf_id=str(data["shelf_id"]),
            catalog_number=int(data["catalog_number"]),
            title=str(data["title"]),
            genre=str(data["genre"]),
            author_name=str(data["author_name"]),
            language_code=str(data.get("language_code", "common")),
            created_year=int(data["created_year"]),
            origin_name=str(data["origin_name"]),
            condition=str(data.get("condition", "intact")),
            text_seed=int(data.get("text_seed", 0)),
            text_plan=dict(data.get("text_plan", {})),
            written_content=dict(data.get("written_content", {})),
            damage_state=dict(data.get("damage_state", {})),
            schema_version=2,
        )

    def public_payload(self) -> dict:
        return {
            "id": self.id,
            "shelf_id": self.shelf_id,
            "catalog_number": self.catalog_number,
            "title": self.title,
            "genre": self.genre,
            "genre_name": GENRES.get(self.genre, self.genre),
            "author_name": self.author_name,
            "language_code": self.language_code,
            "created_year": self.created_year,
            "origin_name": self.origin_name,
            "condition": self.condition,
            "form": self.text_plan.get("form", ""),
            "audience": self.text_plan.get("audience", ""),
            "length_class": self.text_plan.get("length_class", ""),
        }


def _choice(seed: int, label: str, values: tuple[str, ...]) -> str:
    return values[_stable_int(seed, label) % len(values)]


def make_book_text_plan(text_seed: int, genre: str,
                        context: dict | None = None) -> dict:
    """Freeze composition choices before any prose is materialized."""
    context = dict(context or {})
    subjects = _TITLE_PARTS[genre][0]
    primary = _choice(text_seed, "primary", subjects)
    remaining = tuple(item for item in subjects if item != primary)
    secondary = _choice(text_seed, "secondary", remaining or subjects)
    length_class = _choice(
        text_seed, "length", ("short", "single_volume", "multi_volume"))
    section_count = {
        "short": 3, "single_volume": 4, "multi_volume": 6,
    }[length_class]
    return {
        "format_version": BOOK_TEXT_PLAN_VERSION,
        "generator_version": "ordinary-books-v2",
        "genre": genre,
        "form": _choice(text_seed, "form", _FORMS[genre]),
        "audience": _choice(text_seed, "audience", _AUDIENCES[genre]),
        "voice": _choice(text_seed, "voice", tuple(_VOICES)),
        "stance": _choice(text_seed, "stance", tuple(_STANCES)),
        "source_mode": _choice(
            text_seed, "source", tuple(_SOURCE_NOTES)),
        "length_class": length_class,
        "themes": [primary, secondary],
        "outline": list(_OUTLINES[genre][:section_count]),
        "context": context,
        "materialization_status": "planned",
    }


def library_book_count(settlement, current_year: int) -> int:
    """Scale holdings without coupling ordinary books to historical events."""
    level = max(0.0, float(settlement.infrastructure.get("library", 0.0)))
    if level < 0.5 or not settlement.alive:
        return 0
    size_base = {"village": 20, "town": 70, "city": 170}.get(
        settlement.size, 40)
    age = max(1, current_year - settlement.founded_year + 1)
    scholarship = max(
        0.0,
        float(settlement.cultural_influence)
        + float(settlement.theoretical_knowledge),
    )
    total = round(
        size_base * (0.55 + 0.7 * min(level, 2.5))
        + age * (1.2 + 0.18 * scholarship)
        + scholarship * 5.0
    )
    return max(20, min(1200, total))


def build_library_catalog(seed: int, settlement, collection_id: str,
                          current_year: int,
                          context: dict | None = None) -> list[LibraryBook]:
    count = library_book_count(settlement, current_year)
    if count == 0:
        return []
    shelf_count = min(
        MAX_LIBRARY_SHELVES,
        max(1, math.ceil(count / BOOKS_PER_SHELF_TARGET)),
    )
    genres = tuple(GENRES)
    result = []
    for index in range(count):
        number = index + 1
        genre = genres[_stable_int(seed, settlement.id, number, "genre") % len(genres)]
        first, second = _TITLE_PARTS[genre]
        title = (
            f"《{first[_stable_int(seed, settlement.id, number, 'title-a') % len(first)]}"
            f"{second[_stable_int(seed, settlement.id, number, 'title-b') % len(second)]}》"
        )
        oldest = max(settlement.founded_year, current_year - 180)
        span = max(1, current_year - oldest + 1)
        created_year = oldest + _stable_int(
            seed, settlement.id, number, "year") % span
        age = current_year - created_year
        condition_roll = _stable_int(seed, settlement.id, number, "condition") % 100
        condition = (
            "fragile" if age > 90 and condition_roll < 24
            else "worn" if age > 35 and condition_roll < 58
            else "intact"
        )
        shelf_number = index % shelf_count + 1
        text_seed = _stable_int(seed, settlement.id, number, "text")
        book_context = dict(context or {})
        events = [
            item for item in book_context.pop("events", [])
            if int(item.get("year", created_year)) <= created_year
        ]
        if events:
            event = events[_stable_int(text_seed, "event") % len(events)]
            book_context["event"] = str(event.get("title", "一件当地旧事"))
            book_context["event_year"] = int(event.get("year", created_year))
        features = list(book_context.pop("features", []))
        if features:
            book_context["feature"] = str(
                features[_stable_int(text_seed, "feature") % len(features)])
        partners = list(book_context.pop("trade_partners", []))
        if partners:
            book_context["trade_partner"] = str(
                partners[_stable_int(text_seed, "partner") % len(partners)])
        result.append(LibraryBook(
            id=f"book_{settlement.id}_{number:04d}",
            collection_id=collection_id,
            settlement_id=settlement.id,
            shelf_id=f"library_shelf_{settlement.id}_{shelf_number:02d}",
            catalog_number=number,
            title=title,
            genre=genre,
            author_name=f"{settlement.name}{_AUTHOR_ROLES[genre]}",
            language_code="common",
            created_year=created_year,
            origin_name=settlement.name,
            condition=condition,
            text_seed=text_seed,
            text_plan=make_book_text_plan(text_seed, genre, book_context),
        ))
    return result


def materialize_library_book(book: LibraryBook) -> str:
    """Generate and cache genre-specific prose on first opening."""
    cached = book.written_content.get("text_cn")
    if cached:
        _ensure_library_book_damage(book)
        return str(cached)
    if not book.text_plan:
        book.text_plan = make_book_text_plan(
            book.text_seed, book.genre, {
                "place": book.origin_name,
                "feature": book.origin_name,
                "event": "一件未注明名称的旧事",
                "event_year": book.created_year,
                "religion": "当地传统",
                "trade_partner": "邻近聚落",
            })
    plan = book.text_plan
    context = {
        "place": book.origin_name,
        "feature": book.origin_name,
        "event": "一件未注明名称的旧事",
        "event_year": book.created_year,
        "religion": "当地传统",
        "trade_partner": "邻近聚落",
        **plan.get("context", {}),
        "primary": plan["themes"][0],
        "secondary": plan["themes"][1],
        "audience": plan["audience"],
    }
    condition_note = {
        "intact": "装订完整，正文大多清晰。",
        "worn": "书页边缘磨损，少量字句已经模糊。",
        "fragile": "纸页脆弱，数处内容因缺叶而中断。",
    }[book.condition]
    templates = _SECTION_TEMPLATES[book.genre]
    sections = []
    for index, heading in enumerate(plan["outline"]):
        paragraph = templates[index].format(**context)
        if index == 0:
            paragraph += _VOICES[plan["voice"]]
        elif index == 1:
            paragraph += _SOURCE_NOTES[plan["source_mode"]]
        elif index == len(plan["outline"]) - 1:
            paragraph += _STANCES[plan["stance"]]
        sections.append({"heading": heading, "text": paragraph})
    front_matter = (
        f"{book.title}\n"
        f"{book.author_name} · {plan['form']} · 写给{plan['audience']}\n"
        f"成书于第 {book.created_year} 年。{condition_note}"
    )
    text = front_matter + "\n\n" + "\n\n".join(
        f"【{section['heading']}】\n{section['text']}"
        for section in sections
    )
    book.written_content = {
        "format_version": BOOK_CONTENT_VERSION,
        "generator_version": plan["generator_version"],
        "front_matter": front_matter,
        "sections": sections,
        "text_cn": text,
    }
    _ensure_library_book_damage(book)
    book.text_plan["materialization_status"] = "ready"
    return text


def _damage_target_ratio(book: LibraryBook) -> float:
    if book.condition == "intact":
        return 0.0
    roll = _stable_int(book.id, book.text_seed, "damage-ratio") % 1001 / 1000
    if book.condition == "worn":
        return 0.05 + 0.10 * roll
    return 0.20 + 0.20 * roll


def _ensure_library_book_damage(book: LibraryBook) -> None:
    """Create persistent lesions without modifying the cached pristine prose."""
    if book.damage_state.get("version") == BOOK_DAMAGE_VERSION:
        return
    sections = book.written_content.get("sections", [])
    lengths = [len(str(section.get("text", ""))) for section in sections]
    total_chars = sum(lengths)
    lesions = []
    lost_chars = 0
    whole_section = None

    if book.condition == "fragile" and sections:
        whole_section = _stable_int(book.id, book.text_seed, "whole-section") % len(sections)
        damage_type = (
            "missing_leaves"
            if _stable_int(book.id, book.text_seed, "whole-kind") % 2 == 0
            else "stuck_pages"
        )
        lesions.append({
            "section_index": whole_section,
            "damage_type": damage_type,
            "start": 0,
            "end": lengths[whole_section],
            "whole_section": True,
        })
        lost_chars += lengths[whole_section]

    target_chars = round(total_chars * _damage_target_ratio(book))
    target_chars = max(target_chars, lost_chars)
    remaining = min(total_chars - lost_chars, target_chars - lost_chars)
    candidates = [index for index in range(len(sections)) if index != whole_section]
    if remaining > 0 and candidates:
        # Give each eligible section one contiguous lesion. Stable weights make
        # the pattern irregular while keeping the actual loss ratio controlled.
        weights = {
            index: 1 + _stable_int(book.id, book.text_seed, index, "weight") % 100
            for index in candidates
        }
        weight_total = sum(weights.values())
        quotas = {
            index: min(lengths[index], remaining * weights[index] // weight_total)
            for index in candidates
        }
        assigned = sum(quotas.values())
        order = sorted(
            candidates,
            key=lambda index: _stable_int(book.id, book.text_seed, index, "remainder"),
        )
        while assigned < remaining:
            progressed = False
            for index in order:
                if assigned >= remaining:
                    break
                if quotas[index] < lengths[index]:
                    quotas[index] += 1
                    assigned += 1
                    progressed = True
            if not progressed:
                break
        partial_types = (
            ("faded_ink", "water_blur")
            if book.condition == "worn"
            else ("faded_ink", "water_blur", "insect_holes", "torn_edge")
        )
        for index in candidates:
            quota = quotas[index]
            if quota <= 0:
                continue
            start = _stable_int(book.id, book.text_seed, index, "start") % (
                lengths[index] - quota + 1)
            damage_type = partial_types[
                _stable_int(book.id, book.text_seed, index, "kind") % len(partial_types)
            ]
            lesions.append({
                "section_index": index,
                "damage_type": damage_type,
                "start": start,
                "end": start + quota,
                "whole_section": False,
            })
        lost_chars += assigned

    active_types = []
    for lesion in lesions:
        if lesion["damage_type"] not in active_types:
            active_types.append(lesion["damage_type"])
    book.damage_state = {
        "version": BOOK_DAMAGE_VERSION,
        "condition": book.condition,
        "target_loss_ratio": round(_damage_target_ratio(book), 3),
        "loss_ratio": round(lost_chars / total_chars, 3) if total_chars else 0.0,
        "readability_ratio": round(1 - lost_chars / total_chars, 3) if total_chars else 1.0,
        "damage_types": active_types,
        "lesions": lesions,
    }


def render_library_book(book: LibraryBook) -> dict:
    """Return the damaged reading view while retaining pristine cached text."""
    materialize_library_book(book)
    _ensure_library_book_damage(book)
    lesions_by_section = {
        int(lesion["section_index"]): lesion
        for lesion in book.damage_state.get("lesions", [])
    }
    visible_sections = []
    for index, section in enumerate(book.written_content.get("sections", [])):
        visible = dict(section)
        lesion = lesions_by_section.get(index)
        if lesion is None:
            visible["status"] = "readable"
        else:
            damage_type = str(lesion["damage_type"])
            damage_label = DAMAGE_LABELS[damage_type]
            visible["damage_type"] = damage_type
            visible["damage_label"] = damage_label
            if lesion.get("whole_section"):
                visible["status"] = "missing"
                visible["text"] = f"〔{damage_label}：本节正文无法展开〕"
            else:
                start, end = int(lesion["start"]), int(lesion["end"])
                text = str(section.get("text", ""))
                visible["status"] = "damaged"
                visible["text"] = text[:start] + f"〔{damage_label}〕" + text[end:]
        visible_sections.append(visible)
    damage_types = list(book.damage_state.get("damage_types", []))
    return {
        "front_matter": book.written_content.get("front_matter", ""),
        "sections": visible_sections,
        "readability_ratio": float(book.damage_state.get("readability_ratio", 1.0)),
        "damage_types": damage_types,
        "damage_labels": [DAMAGE_LABELS[item] for item in damage_types],
    }
