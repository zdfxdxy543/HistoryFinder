"""Deterministic in-world text stored by written evidence."""

from __future__ import annotations

import hashlib
import copy as copy_module


BUILDING_NAMES = {
    "temple": "神殿",
    "library": "图书馆",
    "market": "大市场",
    "fortification": "城墙与防御工事",
    "aqueduct": "引水渠",
    "palace": "领主大厅",
}


def _stable_choice(seed: int, evidence_id: str, key: str,
                   options: list[str]) -> str:
    payload = f"{seed}|{evidence_id}|{key}".encode("utf-8")
    index = int(hashlib.sha256(payload).hexdigest()[:8], 16)
    return options[index % len(options)]


def _passage(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text}


def _generic_passages(event, subtype: str, seed: int,
                      document_key: str) -> list[dict]:
    description = event.details.get("description_cn", "")
    passages = [_passage("heading", event.title)]
    if description:
        passages.append(_passage("body", description))
    passages.append(_passage("body", _stable_choice(
        seed, document_key, f"{subtype}:generic_note", [
            "页边留有两处补记，正文与补记的书写时间可能不同。",
            "若干姓名以缩写记载，抄录者没有展开其全称。",
            "正文后附有一列数量记号，其中一项已被划去。",
            "记录者在末段改用较淡的墨水，原因未作说明。",
            "本页引用了另一份已经缺失的账册，未抄录其全文。",
        ])))
    passages.append(_passage("closing", _stable_choice(
        seed, document_key, f"{subtype}:generic_closing", [
            "此页所录，留待核验。",
            "记录到此中止，余页次序未定。",
            "末行注明：异议应另页附入，不得刮改原文。",
            "卷末印记残缺，复核者只留下一个短签。",
        ])))
    return passages


def _literary_passages(seed: int, document_key: str, work_title: str,
                       author: str, genre: str) -> list[dict]:
    motifs = {
        "epic": ["城门", "远征", "失落的旗帜", "归乡者"],
        "drama": ["空置的座位", "两份相反的证词", "未拆的封印", "夜间钟声"],
        "chronicle": ["旧市场", "河岸界碑", "历任书记", "重修的城墙"],
        "lyric_cycle": ["井水", "麦穗", "长路", "冬夜灯火"],
    }
    motif = _stable_choice(seed, document_key, "literary_motif",
                           motifs.get(genre, motifs["epic"]))
    setting = _stable_choice(seed, document_key, "literary_setting", [
        "雨后的城墙", "收获后的空田", "结冰前的渡口", "正午的旧市场",
        "封门后的档案室", "雾中的山道", "退潮后的石堤", "节庆散场的广场",
    ])
    keepsake = _stable_choice(seed, document_key, "literary_keepsake", [
        "缺角的铜扣", "褪色的布带", "刻错一笔的木牌", "没有署名的短笺",
        "裂开的陶制印章", "磨平齿纹的钥匙", "缝过三次的袖章", "写反地名的路牌",
    ])
    witness = _stable_choice(seed, document_key, "literary_witness", [
        "守桥人", "磨坊学徒", "退役的号手", "替人写信的书记",
        "沿街补锅的匠人", "看守粮仓的寡妇", "在渡口长大的船夫", "失明的老歌者",
    ])
    absent = _stable_choice(seed, document_key, "literary_absent", [
        "没有列入名册的搬运者", "未能返乡的信使", "被删去姓氏的见证人",
        "只在账簿边角出现的孩子", "把工具借给远征者的石匠", "拒绝签名的医者",
    ])
    weather = _stable_choice(seed, document_key, "literary_weather", [
        "连雨刚停", "北风卷起灰土", "河面升起薄雾", "第一场霜落下",
        "暑气仍压在屋瓦上", "远雷越过丘陵", "融雪漫过旧路", "月光照亮空井",
    ])
    dispute = _stable_choice(seed, document_key, "literary_dispute", [
        "谁有权替死者说出最后一句话", "一份旧誓言是否仍约束后来的人",
        "胜利者能否独自为街道命名", "沉默是否也能算作证词",
        "归还物件是否等同于偿还承诺", "被重复百年的故事是否仍属于最初的讲述者",
    ])
    sound = _stable_choice(seed, document_key, "literary_sound", [
        "三短一长的钟声", "空车轮碾过石路的回响", "远处磨盘忽停的摩擦声",
        "渡船碰撞木桩的闷响", "集市棚布被风扯动的拍击声", "屋檐水落入铜盆的节拍",
    ])

    def choose(key: str, options: list[str]) -> str:
        return _stable_choice(seed, document_key, key, options)

    if genre == "drama":
        body = [
            _passage("body", f"人物：{witness}、归来的使者、抄写员、{absent}的亲属与两名轮值市民。"),
            _passage("body", f"第一场：{weather}。{setting}下，众人围绕{motif}争论{dispute}。"),
            _passage("body", f"{witness}：我只听见{sound}，没有看见是谁先越过门槛。"),
            _passage("body", f"使者展示{keepsake}，却拒绝说明它是在路上拾得还是受人托付。"),
            _passage("body", "抄写员把证词分写在两块板上，说并列不等于赞同其中任何一方。"),
            _passage("body", f"亲属念出{absent}留下的半句话，末尾被观众席的争吵盖过。"),
            _passage("body", f"第二场：{choose('drama_signal', ['城门落锁', '灯芯熄灭', '鼓手漏了一拍', '雨水浸过台阶'])}。两名市民给出相反的先后次序。"),
            _passage("body", f"第一市民追问：{choose('drama_question', ['若记忆会变，为何还要重演', '若印记可信，为何落款不同', '若无人认领，物件是否仍有主人', '若两人都诚实，矛盾从何而来'])}？"),
            _passage("body", f"第二市民回答：{choose('drama_answer', ['让不同的人轮流说出所见', '把无法确认的地方留白', '先保存争议，再讨论裁断', '不要替沉默者补写姓名'])}。"),
            _passage("body", f"第三场：旧卷被朗读时，台上人物逐句补入{choose('drama_omission', ['伤者与搬运者', '守夜者与烧饭人', '失踪者与临时工匠', '债主与未领报酬者'])}。"),
            _passage("body", f"{witness}把{keepsake}放到桌面中央，请下一位保管者先写下自己不知道的事。"),
            _passage("body", f"末场：{sound}再次响起，物件、证词和空白名册仍并排放着；幕布在裁断前落下。"),
        ]
    elif genre == "chronicle":
        body = [
            _passage("body", f"序：编者把{choose('chron_sources', ['旧账、碑铭与口述', '税册、墓记与家谱', '工匠名录、路标与残信', '庭审笔记、仓单与歌谣'])}按年排列，互相冲突者并列保存。"),
            _passage("body", f"第一卷追索{motif}附近的街巷、水道和旧称，并标出{choose('chron_boundary', ['三段有争议的边界', '两条已经改道的沟渠', '一处反复易名的广场', '四座只存于口述的门楼'])}。"),
            _passage("body", f"{witness}在{setting}重新核线，发现{choose('chron_mismatch', ['界石方位与账册不合', '道路宽度比旧图少半步', '两册地租簿使用不同地名', '桥墩上的年份被后刻覆盖'])}。"),
            _passage("body", f"第二卷抄录{choose('chron_economy', ['歉收、征收与粮价', '工钱、木料与盐价', '渡税、车数与仓耗', '种量、雨日与磨坊产量'])}，所有互异数字均未删去。"),
            _passage("body", f"同卷附有{choose('chron_witnesses', ['磨坊主、佃户和税吏', '船夫、商人和门吏', '医者、掘墓人和祭司', '石匠、书记和守夜人'])}的说法；编者拒绝把它们合成一个数字。"),
            _passage("body", f"第三卷列出{choose('chron_works', ['城门修缮与负责工匠', '水渠清淤与轮值劳工', '市场迁建与摊位编号', '粮仓扩建与木料来源'])}。"),
            _passage("body", f"名录旁夹着一张关于{keepsake}的领物单，领取者可能是{absent}。"),
            _passage("body", f"第四卷并列{choose('chron_conflict', ['两份战争报告', '三份继承告示', '一份判词与两份证词', '官署清册和商会账簿'])}，没有删去相互冲突的句子。"),
            _passage("body", f"附录只收录由{choose('chron_confirm', ['两名见证者', '一份账册和一处碑记', '三个互不相识的讲述者', '原件与早期抄本'])}共同确认的姓名，其余另列待考。"),
            _passage("body", f"第五卷记录{choose('chron_daily', ['节庆、婚约与诉讼', '迁居、借贷与学徒契约', '井水分配与夜间巡逻', '丧葬、集市与儿童歌谣'])}中普通居民留下的短句。"),
            _passage("body", f"第六卷解释{sound}为何在不同城区被赋予不同含义，并保留旧称。"),
            _passage("body", f"末卷列出依据：{choose('chron_counts', ['七册账簿、四方碑铭与两封残信', '五卷税册、九次口述与一张旧图', '三本名录、六块木牌与十一则证词', '八份仓单、两座墓记与四首旧歌'])}。"),
            _passage("body", f"编者说明：关于{dispute}的缺失年份一律留白，不以推测补齐。"),
        ]
    elif genre == "lyric_cycle":
        body = [
            _passage("body", f"其一：{motif}映着{choose('lyric_light', ['清晨的浅光', '雨前的暗云', '迟来的月色', '炉火的红光'])}，最先醒来的人没有留下姓名。"),
            _passage("body", f"其二：{weather}，风越过{setting}，把尘土带进一封未写完的信。"),
            _passage("body", f"其三：孩子拾到{keepsake}，问{witness}它为何比故事中的名字更长久。"),
            _passage("body", f"其四：{choose('lyric_market', ['集市散去', '渡船离岸', '祭仪结束', '粮仓封门'])}以后，秤盘仍在衡量无人认领的承诺。"),
            _passage("body", f"其五：归人摸到{choose('lyric_mark', ['门上的旧凿痕', '井沿的绳槽', '桥栏的刀痕', '石阶的车辙'])}，却认不出后来刻上的新字。"),
            _passage("body", f"其六：有人伴着{sound}重复一首歌，每唱一遍便少一个名字，多一处停顿。"),
            _passage("body", f"其七：{choose('lyric_depth', ['井绳', '河湾', '空罐', '地窖石阶'])}把昨夜的回声送回更深的地方。"),
            _passage("body", f"其八：{choose('lyric_crop', ['麦穗低头', '芦苇弯腰', '果枝触地', '苔藓伏在碑面'])}不是因为认罪，而是风从所有方向经过。"),
            _passage("body", f"其九：{absent}没有归来，旧屋的门槛仍按同样的位置磨损。"),
            _passage("body", f"其十：道路向{choose('lyric_roads', ['山口与河谷', '旧城与新田', '港湾与高地', '墓园与市场'])}延伸，离去与归来共用一块路标。"),
            _passage("body", f"其十一：歌者把关于{dispute}的最后一节交给听众，不规定悲伤或庆贺。"),
            _passage("body", f"尾声：抄写者在{choose('lyric_blank', ['末行', '页边', '两节之间', '题名之后'])}留出空白，供后来者续写。"),
        ]
    else:
        body = [
            _passage("body", f"开篇：歌者在{setting}请求听众记住{motif}，并暂缓判断{dispute}。"),
            _passage("body", f"第一歌讲述队伍离城时携带{choose('epic_supplies', ['井水、烤谷与三面旗帜', '盐肉、绳索与两架空车', '药草、干柴与一只铜号', '种子、铁锹与四卷地图'])}。"),
            _passage("body", f"{weather}，年长向导凭{choose('epic_old_route', ['星位', '旧界石', '树皮风向', '驮兽脚印'])}辨路，年轻向导却相信{choose('epic_new_route', ['河声', '新绘地图', '商队传言', '山顶烟迹'])}。"),
            _passage("body", f"第二歌列出{choose('epic_places', ['渡口、山隘和废井', '盐道、牧场和旧营地', '石桥、密林和边界塔', '浅滩、坡田和烧毁村舍'])}使用的不同地名。"),
            _passage("body", f"负伤者把{keepsake}交给{witness}，请其只转交物件，不替自己编造遗言。"),
            _passage("body", f"第三歌写两位首领对{choose('epic_oath', ['同一誓言', '撤退命令', '分粮规则', '俘虏交换'])}作出相反解释。"),
            _passage("body", f"队伍分成两列，却仍{choose('epic_shared', ['从同一口锅取食', '共用最后一捆柴', '轮换照料伤员', '在同一张图上标路'])}。"),
            _passage("body", f"第四歌不写胜负，只按{choose('epic_order', ['担架抵门', '号角停响', '旗帜归还', '医者点灯'])}的次序记录伤者。"),
            _passage("body", f"第五歌转述等待者的声音：有人寻找亲属，有人询问{choose('epic_debt', ['借出的工具', '未付的工钱', '托带的信件', '无人照料的田地'])}。"),
            _passage("body", f"幸存者归乡时发现{choose('epic_change', ['街道已经换名', '城门改了方向', '旧井被石板封住', '市场迁到河岸'])}。"),
            _passage("body", f"第六歌让三位归人分别讲述{sound}响起时的方位；三段叙述互不相合。"),
            _passage("body", f"尾声之前，歌者念出能够确认的姓名，并为{absent}保留一段停顿。"),
            _passage("body", f"终歌要求听众在下一次吟诵中重新讨论{dispute}，不得把空白当作答案。"),
        ]
    return [
        _passage("heading", f"《{work_title}》"),
        _passage("attribution", f"作者：{author}。"),
        *body,
        _passage("closing", "抄本校记：断句与异文见页边小字。"),
    ]


def _theoretical_passages(seed: int, document_key: str, work_title: str,
                          author: str, field: str) -> list[dict]:
    material = {
        "mechanics": {
            "terms": "力、支点、臂长与负载",
            "subjects": ["石块与木臂", "井桶与绞盘", "城门配重", "货车轮轴"],
            "changes": ["木臂长度", "支点位置", "轮轴直径", "绳索绕行次数"],
            "observations": ["所需拉力随比例改变", "起动与持续转动所需的力不同", "支点偏移会放大一侧负载", "绳索弯折会消耗部分作用"],
            "applications": ["井架", "城门绞盘", "石料吊装", "粮仓升降架"],
            "limits": ["潮湿绳索", "不规则石块", "磨损的轴孔", "倾斜的支架"],
        },
        "agronomy": {
            "terms": "土性、轮作、休耕与种子留选",
            "subjects": ["谷物与豆类轮作", "坡田保水", "种子留选", "畜肥腐熟"],
            "changes": ["播种次序", "沟渠间距", "留种颗粒大小", "施肥时节"],
            "observations": ["连续种植会降低第三年穗粒", "横沟能够延缓坡面失水", "饱满种粒的出苗更整齐", "未腐熟肥料会灼伤幼苗"],
            "applications": ["田区划分", "播种历", "粮仓种子管理", "坡地水渠"],
            "limits": ["突发洪水", "迁徙畜群", "不同坡向", "连续虫害"],
        },
        "medicine": {
            "terms": "脉息、热度、创口污染与药材剂量",
            "subjects": ["创口清洗", "热病隔离", "草药剂量", "饮水煮沸"],
            "changes": ["器具处理方式", "病床间距", "每次药量", "煮沸持续时间"],
            "observations": ["清洁器具对应较少的创口恶化", "分室照料减少了相邻病床发热", "过量药汁会引起呕吐", "静置饮水仍会出现沉渣"],
            "applications": ["军营伤员", "产房器具", "热病住处", "公共水井"],
            "limits": ["伤势轻重", "病人原有体力", "药材批次差异", "照料人数不足"],
        },
        "astronomy": {
            "terms": "影长、方位、季节与星位周期",
            "subjects": ["正午影长", "星体升起方位", "月相周期", "夜间漏刻校正"],
            "changes": ["观测日期", "标杆高度", "地平参照点", "记录间隔"],
            "observations": ["相近日期的影长会再次接近", "星体升起点沿地平缓慢移动", "月相间隔存在可记录周期", "漏刻快慢随温度略有变化"],
            "applications": ["播种历", "远行定向", "夜间计时", "节庆日期校订"],
            "limits": ["地面倾斜", "标杆移动", "连续阴天", "地平线被山体遮挡"],
        },
    }.get(field, {
        "terms": "观察、度量、假设与反例",
        "subjects": ["材料试制", "重复测量", "比例比较", "失败记录"],
        "changes": ["一种材料", "一个步骤", "测量次序", "记录人员"],
        "observations": ["重复测量会暴露首次误差", "更换记录人后数字略有偏移", "失败位置常集中在连接处", "共同量具能减少地点差异"],
        "applications": ["工匠试制", "公共工程", "仓储计量", "道路测绘"],
        "limits": ["缺少共同量具", "样品数量过少", "材料来源不一", "记录时间不一致"],
    })
    subject = _stable_choice(seed, document_key, "theory_subject", material["subjects"])
    changed = _stable_choice(seed, document_key, "theory_change", material["changes"])
    observation = _stable_choice(
        seed, document_key, "theory_observation", material["observations"])
    application = _stable_choice(
        seed, document_key, "theory_application", material["applications"])
    limitation = _stable_choice(
        seed, document_key, "theory_limit", material["limits"])
    instrument = _stable_choice(seed, document_key, "theory_instrument", [
        "刻度木尺和配重", "分栏记录板和计时漏壶", "带封记的样品罐",
        "校准过的秤与细绳", "固定石台和方向线", "编号木签与对照表",
    ])
    repetition = _stable_choice(seed, document_key, "theory_repetition", [
        "三次", "四次", "五次", "两个地点各三次", "由两组人分别完成",
    ])
    anomaly = _stable_choice(seed, document_key, "theory_anomaly", [
        "一次结果与其余记录方向相反", "更换记录者后数值整体偏高",
        "雨后取得的样品表现异常", "最大样品没有遵循较小样品的比例",
        "一组记录因封记破损而不能采用", "第二地点的结果只在清晨能够重复",
    ])
    comparison = _stable_choice(seed, document_key, "theory_comparison", [
        "旧有做法", "未经处理的对照组", "相邻地点的同类记录",
        "不同尺寸的样品", "由另一名记录者取得的数据",
    ])
    return [
        _passage("heading", f"《{work_title}》"),
        _passage("attribution", f"作者：{author}。"),
        _passage("body", f"序言：本书讨论{material['terms']}，并区分观察、推论和传闻。"),
        _passage("body", f"定义：本卷以{subject}为主要对象，为{material['terms']}分别规定记号。"),
        _passage("body", f"试验布置：使用{instrument}，每轮只改变{changed}，其余条件写入对照栏。"),
        _passage("body", f"记录栏：将{subject}与{comparison}并列，空缺不得用估计值补齐。"),
        _passage("body", f"观察一：{observation}；这一结果在本卷中重复{repetition}。"),
        _passage("body", f"观察二：改换{changed}后，差异首先出现在{_stable_choice(seed, document_key, 'theory_difference', ['起始阶段', '中段读数', '最大样品', '第二日记录', '边缘样本'])}。"),
        _passage("body", f"数据整理：分别保留{repetition}记录的最大值、最小值和中间值，并注明{instrument}的校准日。"),
        _passage("body", f"主要推论：关于{subject}的变化不能只由名称判断，必须结合{changed}和对照记录。"),
        _passage("body", f"反例：{anomaly}；作者没有删除此项，而把它列为下一轮试验的起点。"),
        _passage("body", f"适用限制：{limitation}会破坏比较。超出这些条件时，本书不保证推论成立。"),
        _passage("body", f"可能用途：{application}。这一用途依据{subject}的记录提出，尚需由工匠另行试制。"),
        _passage("body", f"验证方法：重做时须保留{changed}、日期、失败结果以及{instrument}的状态。"),
        _passage("body", f"复核办法：由未参加原试验的人用{comparison}复查，并把偏差写在原表旁。"),
        _passage("body", f"后续问题：{subject}的关系是否会随{_stable_choice(seed, document_key, 'theory_scale', ['季节', '尺度', '材料来源', '地点', '操作者'])}改变，应另立条目。"),
        _passage("closing", "结语：本卷只提出可检验的关系，不把尚未试制的用途称为既成技术。"),
    ]


def build_written_content(event, subtype: str, seed: int,
                          evidence_id: str, variant: int = 0,
                          is_copy: bool = False) -> dict:
    """Build the words an in-world document claims, separate from truth."""
    base_subtype = subtype.removesuffix("_copy") if is_copy else subtype
    document_key = f"{evidence_id}|variant:{variant}"
    details = event.details
    year = event.year
    passages: list[dict]

    if base_subtype == "founding_charter":
        founder = details.get("founder", "诸位立约者")
        settlement = details.get("settlement_name", "此地")
        grant = _stable_choice(seed, document_key, "charter_grant", [
            "水井、道路与外田由共同劳作的人使用。",
            "居所、耕地与水源的界线须由见证人共同确认。",
            "城门以内的争议由立约者与居民代表共同裁断。",
        ])
        passages = [
            _passage("heading", f"{settlement}立约书"),
            _passage("body", f"第{year}年，{founder}与随行者在{settlement}立下此约。"),
            _passage("body", grant),
            _passage("closing", f"立约人：{founder}。见证者名列封印之下。"),
        ]
    elif base_subtype == "war_record":
        attacker = details.get("attacker", "进攻者")
        defender = details.get("defender", "守城者")
        outcome = details.get("outcome", "stalemate")
        reports = {
            "attacker_victory": f"军务书记记录：{attacker}的军队已经进入{defender}，城内清点仍未结束。",
            "defender_victory": f"守城官呈报：{defender}的守军迫使{attacker}撤离城墙与外营。",
            "stalemate": f"军务书记记录：{attacker}与{defender}均已收兵，阵地归属仍无定论。",
        }
        passages = [
            _passage("heading", f"第{year}年军务抄录"),
            _passage("body", reports.get(outcome, reports["stalemate"])),
            _passage("closing", "伤亡、俘虏与物资损耗另见附页。"),
        ]
    elif base_subtype in ("literary_manuscript", "traveling_literary_copy"):
        passages = _literary_passages(
            seed,
            document_key,
            details.get("work_title", "无题文稿"),
            details.get("author_name", "佚名"),
            details.get("genre", "epic"),
        )
        if base_subtype == "traveling_literary_copy":
            passages.append(_passage(
                "copy_note",
                f"抄写记：此本在{details.get('target_name', '外地')}重新装订，"
                "个别词句依当地读法改写。"))
    elif base_subtype == "literary_commentary":
        title = details.get("work_title", "无题文稿")
        opening_issue = _stable_choice(seed, document_key, "commentary_opening", [
            "开篇地名有两种写法", "开篇人物在晚期本中多出一个称号",
            "首节的两行在不同抄本中次序相反", "题名下的作者署名使用了较新的字形",
        ])
        performance_note = _stable_choice(seed, document_key, "commentary_performance", [
            "重复句可能用于公开吟诵", "短句可能是合唱者的应答",
            "两段押韵文字可能来自节庆改编", "行尾记号可能提示演奏停顿",
        ])
        composite = _stable_choice(seed, document_key, "commentary_composite", [
            "某些人物可能由多人合并而成", "同一称号可能先后属于不同人物",
            "叙述者可能把两次旅程写成一次", "作品中的城市可能混合了数处地貌",
        ])
        passages = [
            _passage("heading", f"《{title}》边注与异文"),
            _passage("body", f"第一条：现存抄本的{opening_issue}，无法仅凭字形决定孰早。"),
            _passage("body", f"第二条：{performance_note}，不宜立即判为抄写错误。"),
            _passage("body", f"第三条：作品使用的{_stable_choice(seed, document_key, 'commentary_terms', ['统治者称号', '地租名称', '城门方位词', '亲属称谓'])}与同时代文书并不完全一致。"),
            _passage("body", f"第四条：{composite}；校者暂未替这些形象指定原型。"),
            _passage("body", f"第五条：较晚抄本增加了关于{_stable_choice(seed, document_key, 'commentary_late', ['战争结局', '继承次序', '远征路线', '祭仪起源'])}的解释，早期本没有此句。"),
            _passage("body", f"第六条：{_stable_choice(seed, document_key, 'commentary_cut', ['节庆表演本删去地理描写', '商旅传抄本缩短人物对话', '神庙藏本改写了誓言', '学徒抄本省略重复歌节'])}，但保留了前后的转折词。"),
            _passage("body", f"第七条：不能把{_stable_choice(seed, document_key, 'commentary_voice', ['角色发言', '合唱段落', '编者按语', '抄写者补句'])}直接视为作者本人的判断。"),
            _passage("closing", "校者按语：以上仅记录文本差异，不裁定作品所述事件是否真实。"),
        ]
    elif base_subtype == "theoretical_treatise":
        passages = _theoretical_passages(
            seed,
            document_key,
            details.get("work_title", "自然原理论"),
            details.get("author_name", "佚名学者"),
            details.get("theory_field", "unknown"),
        )
    elif base_subtype == "lecture_notes":
        field_name = details.get("theory_field_name", "自然哲学")
        title = details.get("work_title", "自然原理论")
        passages = [
            _passage("heading", f"《{title}》讲学笔记"),
            _passage("body", f"第一讲：{field_name}中的“{_stable_choice(seed, document_key, 'lecture_term', ['尺度', '对照', '误差', '重复', '样品'])}”必须先给出可重复使用的定义。"),
            _passage("body", f"第二讲：观察与解释用{_stable_choice(seed, document_key, 'lecture_layout', ['左右两栏', '黑红两色', '正文和页边', '编号木牌与总表'])}分开，失败结果不得删去。"),
            _passage("body", f"第三讲：学生以{_stable_choice(seed, document_key, 'lecture_groups', ['两人一组', '三组互换', '不同量具', '匿名记录'])}重复同一测量，并比较差异。"),
            _passage("body", f"第四讲：一个例子得到的推论，至少用{_stable_choice(seed, document_key, 'lecture_checks', ['两种材料', '另一个地点', '三种尺寸', '不同季节的旧数据'])}检验。"),
            _passage("body", f"第五讲：工匠提出的{_stable_choice(seed, document_key, 'lecture_change', ['材料替换', '尺寸改动', '操作顺序', '失败补救'])}应另列，不得倒写成作者原先的预言。"),
            _passage("body", f"课后问题：关于《{title}》的哪些结论只在{_stable_choice(seed, document_key, 'lecture_limit', ['特定季节', '某种尺度', '干燥材料', '固定地点'])}成立？"),
            _passage("closing", "笔记末尾列有借阅者姓名与归还日期。"),
        ]
    elif base_subtype == "research_notes":
        discovery = details.get("discovery_name", event.title)
        materials = _stable_choice(seed, document_key, "research_materials", [
            "硬木、铜钉、麻绳与配重", "黏土、炭粉、细砂与封泥",
            "药草、净水、布条与陶罐", "石料、木轴、铁箍与油脂",
            "种粒、土样、灰肥与量斗", "玻璃片、刻尺、灯油与黑布",
        ])
        first_failure = _stable_choice(seed, document_key, "research_failure", [
            "连接处在承受负载后松脱", "样品冷却后出现裂纹",
            "读数在第三次操作时明显偏移", "潮湿材料使试验无法复现",
            "对照组的结果反而更稳定", "封口在一夜后失去气密",
        ])
        revision = _stable_choice(seed, document_key, "research_revision", [
            "缩短尺寸并加固边缘", "更换材料来源并重新称量",
            "调换步骤次序", "增加一组未经处理的对照",
            "把操作人数减为两人", "延长静置时间并遮挡风口",
        ])
        passages = [
            _passage("heading", f"关于“{discovery}”的试验札记"),
            _passage("body", details.get("description_cn", "本页记录了数次观察与试验。")),
            _passage("body", f"材料表：本轮使用{materials}，每批来源与重量分别登记。"),
            _passage("body", f"第一次试制失败：{first_failure}。失败样品没有丢弃。"),
            _passage("body", f"第二次试制选择{revision}，结果可以重复，但仍有一项读数不稳定。"),
            _passage("body", f"第三次试制由{_stable_choice(seed, document_key, 'research_replicator', ['另一组工匠', '两名学徒', '未参加设计的书记', '外地来访者'])}独立完成，主要趋势相近。"),
            _passage("body", f"书记保留{_stable_choice(seed, document_key, 'research_archive', ['失败草图', '破裂样品', '原始计数板', '被否决的尺寸表'])}，以区分必要结构和偶然改动。"),
            _passage("closing", "目前只能确认样品能够重复制成；长期效果仍需继续记录。"),
        ]
    elif base_subtype == "reconstruction_account":
        building = details.get("building_name", "受损设施")
        passages = [
            _passage("heading", f"第{year}年{building}修缮账"),
            _passage("body", _stable_choice(seed, document_key, "reconstruction_material", [
                "回收石料、旧木梁和新制金属件分别登记，不得混列。",
                "可再用构件以红记号标出，裂损构件另堆复验。",
                "新石料按采石场分栏，旧石料按拆取位置编号。",
                "木梁、瓦片和铁件分别称量，途中损耗由运送人签记。",
            ])),
            _passage("body", _stable_choice(seed, document_key, "reconstruction_labor", [
                "工匠口粮按实际出工日数发放，缺勤处留空。",
                "石匠、木匠和搬运者分别记工，不以总人数代替。",
                "夜间加固和白日砌筑使用不同工册，月底合验。",
                "受伤停工者仍领取半份口粮，其姓名附在右栏。",
            ])),
            _passage("closing", "完工后由库房书记复核余料。"),
        ]
    elif base_subtype == "relief_inventory":
        donor = details.get("donor_name", "外地车队")
        recipient = details.get("recipient_name", "受灾聚落")
        passages = [
            _passage("heading", f"送抵{recipient}的物资清单"),
            _passage("body", f"登记来自{donor}的谷物、木料、药材和钱币。"),
            _passage("body", _stable_choice(seed, document_key, "relief_check", [
                "卸货时按车逐批复秤，破损容器另列于右栏。",
                "谷物先验封记再称重，受潮部分不得计入足额。",
                "药材按包清点，缺签者由运送人与接收者共同复看。",
                "木料按长度分堆，途中折损与原有短料分栏记录。",
            ])),
            _passage("closing", "接收者与运送者的印记并列于页脚。"),
        ]
    elif base_subtype == "religious_text":
        refrain = _stable_choice(seed, document_key, "religious_refrain", [
            "守火者应记住来路，也应为后来者留下名字。",
            "石会风化，誓言须由活着的人一再见证。",
            "在晨光照到门槛时，众人依次献水与谷粒。",
        ])
        passages = [
            _passage("heading", "仪式诵文"),
            _passage("body", refrain),
            _passage("body", _stable_choice(seed, document_key, "religious_response", [
                "领诵者读一遍，列席者重复末句三遍。",
                "守灯者读首句，门边众人依次回答自己的名字。",
                "献水之后全体静默一刻，再由年长者续读末段。",
                "每读完一节便移动一枚石子，漏读者不得自行补词。",
            ])),
            _passage("closing", "此抄本供仪式中轮流诵读。"),
        ]
    elif base_subtype == "rebel_manifesto":
        cause = details.get("cause", "overtaxation")
        grievances = {
            "overtaxation": "仓中谷物已经见底，征收者却仍要求下一季的份额。",
            "famine": "田地歉收而粮仓紧闭，挨饿者得不到应有的救济。",
            "succession": "继承之名未经见证，新的命令不应被视作共同的约定。",
            "religious": "旧有的祭仪受到禁止，守誓者被逐出集会之地。",
        }
        passages = [
            _passage("heading", "致城门内外诸人的公开书"),
            _passage("body", grievances.get(cause, grievances["overtaxation"])),
            _passage("body", _stable_choice(seed, document_key, "manifesto_demand", [
                "我们要求公开账册，并由居民推举见证人。",
                "我们要求重开粮仓，由各街区共同清点余粮。",
                "我们要求暂停征收，直到旧令和新令当众核对。",
                "我们要求被拘者出庭答辩，并公布指控者姓名。",
            ])),
            _passage("closing", "愿意作证者，可在市场钟响后留下姓名。"),
        ]
    elif base_subtype == "construction_record":
        building_type = details.get("building_type", details.get("outcome_type"))
        building = BUILDING_NAMES.get(building_type, "一处公共建筑")
        passages = [
            _passage("heading", f"{building}营造记录"),
            _passage("body", f"第{year}年开工。石料、木料和工匠口粮按旬登记。"),
            _passage("body", _stable_choice(seed, document_key, "construction_drawing", [
                "图中双线表示承重墙，圆记号标出立柱位置。",
                "东侧地基改深半尺，原因写在第三张剖面图旁。",
                "木梁按长度编号，榫口不合者以空心记号标出。",
                "灰浆配比由两名工匠分别记录，数字不合处暂未涂改。",
                "排水沟以短斜线表示，完工复测数字写在原图下方。",
                "拆下的旧构件用红点标记，新制部分使用交叉记号。",
            ])),
            _passage("closing", "完工后的余料须交回公共库房。"),
        ]
    elif base_subtype == "trade_ledger":
        goods = details.get("goods") or _stable_choice(
            seed, document_key, "trade_goods", [
                "谷物与硬木", "铁器与工具", "陶器与纺织品",
                "盐、香料与染料", "马匹与皮革", "药材与蜂蜡",
                "铜锭与石料", "酒、干果与羊毛",
            ])
        passages = [
            _passage("heading", f"第{year}年往来账"),
            _passage("body", f"本期登记：{goods}。入库与出库分别记在左右两栏。"),
            _passage("body", _stable_choice(seed, document_key, "trade_audit", [
                "每十份抽取一份复秤；短缺之数记入末栏。",
                "封记破损的货包不得直接入库，须由双方经手人重验。",
                "钱币按铸地分栏，磨损严重者按重量而不按枚数计算。",
                "赊欠项目注明担保人与归还日期，不并入当日实收。",
                "途中损耗由车队和仓吏各记一次，月底对照差额。",
            ])),
            _passage("closing", "经手人和见证人的印记留在页脚。"),
        ]
    elif base_subtype == "succession_decree":
        old_ruler = details.get("old_ruler", "前任领主")
        new_ruler = details.get("new_ruler", "继任者")
        passages = [
            _passage("heading", "关于权柄交接的告示"),
            _passage("body", f"自第{year}年起，{old_ruler}所持印记交由{new_ruler}保管。"),
            _passage("body", _stable_choice(seed, document_key, "succession_order", [
                "库房、城门与征收官须在见证人面前重验旧账。",
                "旧印停用三日，新印样式张贴于各门供书记核对。",
                "尚未结清的契约维持原状，争议项目另交议事者复审。",
                "卫队、仓吏与税吏分别宣读名册，不得以口头传令替代。",
            ])),
            _passage("closing", "此令抄送各门，并以同式印记为凭。"),
        ]
    elif base_subtype == "census_record":
        milestone = details.get("milestone", "若干")
        passages = [
            _passage("heading", f"第{year}年户口清册"),
            _passage("body", f"本轮清点合计约{milestone}人；迁入、迁出与缺报另列。"),
            _passage("body", _stable_choice(seed, document_key, "census_method", [
                "每户按居所、可劳作人数和需供养人数登记。",
                "沿街清点与粮册户名互相核对，暂居者另列。",
                "同名者附记职业和街区，失踪者保留到下一轮复查。",
                "学徒、旅客和季节劳工不得并入房主家属栏。",
            ])),
            _passage("closing", "重复姓名须在下次清点时复核。"),
        ]
    elif base_subtype == "tax_record":
        economic_type = details.get(
            "economic_type", details.get("outcome_type", "unknown"))
        note = {
            "boom": "本期入库数高于旧例，新增货摊与车队另页登记。",
            "bust": "本期多户申请缓征，欠额不得与实收混记。",
        }.get(economic_type, _stable_choice(
            seed, document_key, "tax_period", [
                "本期实收、欠额与减免分别登记。",
                "本期以谷物缴纳者增多，折价仍沿用上季标准。",
                "两处街区尚未完成清点，暂不并入总额。",
                "商队税与田地税分别汇总，劳役折抵另附一页。",
            ]))
        passages = [
            _passage("heading", f"第{year}年征收簿"),
            _passage("body", note),
            _passage("body", _stable_choice(seed, document_key, "tax_accounting", [
                "谷物、钱币与劳役不得折为同一栏。",
                "减免须写明批准人和期限，不得只在总数中扣除。",
                "退回的劣币按重量登记，不计入已经结清的户项。",
                "迟缴情形附记原因，复核前仍列为欠额。",
            ])),
            _passage("closing", "页末总数须由两名书记分别复算。"),
        ]
    elif base_subtype == "birth_record":
        person = details.get("person_name", "一名新生儿")
        parent = details.get("parent_name", "其家人")
        passages = [
            _passage("heading", "出生登记"),
            _passage("body", f"第{year}年，登记新生儿{person}，家属为{parent}。"),
            _passage("closing", "登记人签记已残缺。"),
        ]
    elif base_subtype == "trial_record":
        passages = [
            _passage("heading", f"第{year}年审理记录"),
            _passage("body", details.get("description_cn", "书记分别记录了指控、证词与答辩。")),
            _passage("body", _stable_choice(seed, document_key, "trial_layout", [
                "证人陈述列于左栏，查验过的物件列于右栏。",
                "相互矛盾的证词逐条编号，没有由书记合并措辞。",
                "拒绝回答的问题仍写入问目，答语位置保持空白。",
                "物件只记录可见状态，关于用途的说法另列在证词之后。",
            ])),
            _passage("closing", "末页判词不在本卷之中。"),
        ]
    elif base_subtype == "marriage_contract":
        passages = [
            _passage("heading", "婚约与财产见证书"),
            _passage("body", details.get("description_cn", "双方在见证人面前订立婚约。")),
            _passage("body", _stable_choice(seed, document_key, "marriage_terms", [
                "双方带来的财物分别列明，不得擅自涂改。",
                "共同经营所得与婚前债务分栏记录，见证者各持一份。",
                "居所、工具和牲畜逐项列明，归还条件写在项目之后。",
                "若一方迁居外地，保管中的契据须交共同见证人封存。",
            ])),
            _passage("closing", "两家印记与见证人印记并列于下。"),
        ]
    elif base_subtype == "exploration_journal":
        passages = [
            _passage("heading", f"第{year}年行路札记"),
            _passage("body", details.get("description_cn", "队伍沿图中路线行进并记录沿途地貌。")),
            _passage("body", _stable_choice(seed, document_key, "exploration_marks", [
                "图上的短线表示一日路程，交叉记号表示不能通行。",
                "沿途水源用空圆标出，苦水和季节水源另加一点。",
                "坡度以携车所需人数估记，不能与正式测量混用。",
                "当地人提供的地名保留原读音，未强行换成旧图名称。",
                "返程所见与去程不合之处以双线圈出。",
            ])),
            _passage("closing", "返程路线尚未誊清。"),
        ]
    elif base_subtype == "omen_record":
        passages = [
            _passage("heading", f"第{year}年天象观察"),
            _passage("body", details.get("description_cn", "观测者绘下了当夜所见的天象。")),
            _passage("body", _stable_choice(seed, document_key, "omen_observers", [
                "图旁意见出自数位记录者，彼此并不一致。",
                "三名观测者分别标出颜色，只有持续时间大致相合。",
                "云层遮挡时段留空，没有按前后位置补画轨迹。",
                "神庙与城墙上的观察方位不同，两份草图并列装订。",
            ])),
            _passage("closing", "此处只记所见，不定吉凶。"),
        ]
    else:
        passages = _generic_passages(
            event, base_subtype, seed, document_key)

    return {
        "format_version": 2,
        "language_code": "common",
        "language_name": "通用语",
        "passages": passages,
    }


def build_written_copy_content(source_content: dict, seed: int,
                               evidence_id: str, copy_index: int,
                               created_year: int, variant: int = 0) -> dict:
    """Derive a copy with deterministic, visible transmission differences."""
    result = copy_module.deepcopy(source_content)
    copy_key = f"{evidence_id}|variant:{variant}"
    result["format_version"] = max(2, int(result.get("format_version", 1)))
    passages = result.setdefault("passages", [])
    body_indexes = [
        index for index, passage in enumerate(passages)
        if passage.get("kind") == "body"
    ]
    mode = _stable_choice(seed, copy_key, "copy_variation", [
        "margin", "lacuna", "correction", "local_gloss",
    ])
    target_index = None
    if body_indexes:
        target_index = body_indexes[
            int(hashlib.sha256(
                f"{seed}|{copy_key}|copy_target".encode("utf-8")
            ).hexdigest()[:8], 16) % len(body_indexes)
        ]

    if mode == "lacuna" and target_index is not None:
        source_text = passages[target_index]["text"]
        visible_start = source_text[:max(8, min(18, len(source_text) // 3))]
        passages[target_index]["text"] = (
            f"{visible_start}……〔抄写者注明：所据母本此处缺损〕")
    elif mode == "margin":
        passages.append(_passage(
            "marginalia",
            _stable_choice(seed, copy_key, "copy_margin", [
                "页边注：此处人名在另一版本中少一笔。",
                "页边注：上一行的次序曾被校读者交换。",
                "页边注：此词按本地读法另有一种写法。",
                "页边注：所据母本在这里留有一行空白。",
            ])))
    elif mode == "correction":
        passages.append(_passage(
            "marginalia",
            _stable_choice(seed, copy_key, "copy_correction", [
                "校字记：一处重复词已经圈出，但没有刮除。",
                "校字记：两行旁加次序记号，正文仍照原样保留。",
                "校字记：末段墨色不同，可能经过第二人复核。",
                "校字记：三个缩写未能展开，暂照字形抄入。",
            ])))
    else:
        passages.append(_passage(
            "marginalia",
            _stable_choice(seed, copy_key, "copy_gloss", [
                "地方释词：文中的旧称在本地通常指北门一带。",
                "地方释词：本地诵读时会省去这一词的末音。",
                "地方释词：此处量词与商会账册中的写法不同。",
                "地方释词：抄写者保留原词，没有换成本地称呼。",
            ])))

    collation = _stable_choice(seed, copy_key, "copy_collation", [
        "逐行核过", "只核对了题名与末段", "由第二名抄写者复看",
        "与一份残本对照", "尚未完成复校", "按朗读声重新断句",
    ])
    passages.append(_passage(
        "copy_note",
        f"抄写记：第{created_year}年重抄；第{copy_index + 1}次校读"
        f"采用“{collation}”的记号。"))
    return result
