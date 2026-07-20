"""
GameREPL：CLI 交互式探险 REPL。
从 main.py 拆出，不变更行为。
"""

import sys
from game.knowledge import PlayerKnowledge
from simulation.world import World
from narrative.llm_interface import generate_narrative, is_llm_available, clear_cache
from narrative.document_reader import read_document
from narrative.context_builder import (
    build_settlement_context,
    build_ruin_context,
    build_evidence_context,
    build_location_investigation_context,
)


class GameREPL:
    """CLI 交互式探险 REPL。"""

    def __init__(self, world: World):
        self.world = world
        self.current_location_id: str | None = None  # 当前所在 settlement_id
        self.visited_locations: set[str] = set()
        self.examined_evidence: set[str] = set()
        self.read_evidence: set[str] = set()
        self.known_events: set[str] = set()
        self.knowledge = PlayerKnowledge()
        # Language progression will extend this set in a later phase.
        self.known_languages: set[str] = {"common"}

    def run(self):
        """进入主循环。"""
        print_welcome(self.world)

        # 默认传送到第一个聚落
        if self.world.settlements:
            first = list(self.world.settlements.values())[0]
            self.travel_to(first.id)

        while True:
            try:
                cmd = input("\n> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n再见，探险家。")
                break

            if not cmd:
                continue

            if cmd in ("quit", "exit", "q"):
                print("再见，探险家。")
                break

            elif cmd in ("help", "h", "?"):
                print_help()

            elif cmd in ("look", "l", "look around"):
                self.cmd_look()

            elif cmd in ("journal", "j"):
                self.cmd_journal()

            elif cmd.startswith("examine "):
                target = cmd[len("examine "):].strip()
                self.cmd_examine(target)

            elif cmd.startswith("read "):
                target = cmd[len("read "):].strip()
                self.cmd_read(target)

            elif cmd.startswith("present "):
                request = cmd[len("present "):].strip()
                self.cmd_present(request)

            elif cmd.startswith("travel to "):
                dest = cmd[len("travel to "):].strip()
                self.cmd_travel(dest)

            elif cmd in ("travel", "go", "map"):
                self.cmd_map()

            elif cmd in ("events", "history"):
                self.cmd_events()

            elif cmd in ("locations", "settlements", "places"):
                self.cmd_locations()

            elif cmd.startswith("search "):
                query = cmd[len("search "):].strip()
                self.cmd_search(query)

            elif cmd in ("cache clear", "clearcache"):
                clear_cache()
                print("[缓存已清空]")

            elif cmd in ("seed", "info", "world info"):
                print(self.world.summary())

            elif cmd in ("reset", "regen"):
                print("提示：退出后用不同 seed 重新运行即可。")

            else:
                print(f"不太懂'{cmd}'是什么意思。输入 help 查看可用的指令。")


    def travel_to(self, settlement_id: str):
        """前往一个聚落。"""
        stl = self.world.get_settlement(settlement_id)
        if stl is None:
            print(f"找不到这个地方。")
            return

        self.current_location_id = settlement_id
        self.visited_locations.add(settlement_id)

        # 根据存活/废墟选择叙事方式
        voice = "neutral_narrative"
        if stl.alive:
            ctx = build_settlement_context(self.world, stl)
            text = generate_narrative(voice, "arrive_at_settlement", ctx)
        else:
            ctx = build_ruin_context(self.world, stl)
            text = generate_narrative(voice, "arrive_at_ruin", ctx)

        print(f"\n{'='*60}")
        print(text)

        # 显示可调查证据
        evidence = self.world.get_all_visible_evidence(settlement_id)
        if evidence:
            print(f"\n你可以调查以下东西（输入 examine <编号>）：")
            for i, evd in enumerate(evidence, 1):
                new_mark = " [新]" if evd.id not in self.examined_evidence else ""
                print(f"  {i}. {_evidence_display_name(evd)}{new_mark}")


    def cmd_look(self):
        """重新查看当前地点。"""
        if self.current_location_id is None:
            print("你在一片陌生的荒野中。不知道该往哪里去。")
            print("试试输入 locations 查看可以去的地方。")
            return

        self.travel_to(self.current_location_id)


    def cmd_examine(self, target: str):
        """检查证据。"""
        if self.current_location_id is None:
            print("你还没有到达任何地方。先 travel 去一个聚落吧。")
            return

        evd = self._resolve_local_evidence(target)
        if evd is None:
            return

        # 检查阶段只传递可观察特征，不读取内部关联事件。
        ctx = build_evidence_context(evd)
        text = generate_narrative(
            "environmental_description", "examine_evidence", ctx)

        print(f"\n--- 检查 {_evidence_display_name(evd)} ---")
        print(text)

        self.examined_evidence.add(evd.id)
        self.knowledge.discover_evidence(evd.id)


    def cmd_read(self, target: str):
        """阅读一份已经检查过的文书。"""
        if self.current_location_id is None:
            print("你还没有到达任何地方。先 travel 去一个聚落吧。")
            return

        evd = self._resolve_local_evidence(target)
        if evd is None:
            return
        if evd.id not in self.examined_evidence:
            print(f"你需要先 examine {_evidence_display_name(evd)}，确认它能否安全展开。")
            return

        result = read_document(evd, self.known_languages)
        print(f"\n--- 阅读 {_evidence_display_name(evd)} ---")
        print(result["text"])
        if result["status"] == "readable":
            self.read_evidence.add(evd.id)
            record = self.world.records.get(evd.source_record_id)
            if record is not None:
                learned = self.knowledge.learn_from_record(
                    record, evd, result.get("readability", 0.0))
                self._print_learned_claims(learned)


    def cmd_present(self, request: str):
        """Show examined evidence to a local scholar or residents."""
        if " to " not in request:
            print("用法：present <编号/名字> to <scholar/villager>")
            return
        target, audience = request.rsplit(" to ", 1)
        audience = audience.strip().lower()
        if audience not in {"scholar", "villager"}:
            print("目前可以向 scholar 或 villager 出示证物。")
            return
        evd = self._resolve_local_evidence(target.strip())
        if evd is None:
            return
        if evd.id not in self.examined_evidence:
            print(f"你需要先 examine {_evidence_display_name(evd)}。")
            return

        record = self.world.records.get(evd.source_record_id)
        clues = evd.provenance_clues
        date_range = clues.get("estimated_year_range")
        if audience == "scholar":
            consultant = self._find_local_consultant()
            if consultant is None:
                print("这里暂时找不到能够辨认这类材料的学者或抄写员。")
                return
            print(f"\n--- 向{consultant.name}出示 {_evidence_display_name(evd)} ---")
            if date_range:
                print(f"{consultant.name}估计其书写或制作年代约在"
                      f"第{date_range[0]}年至第{date_range[1]}年之间。")
            if evd.is_copy_of:
                print(f"{consultant.name}注意到装订和笔迹不一致，认为它可能是转抄本。")
            if record is None:
                print("仅凭这些材料与加工痕迹，还不能把它归到某一件历史事件。")
                return
            reading = read_document(evd, {record.language_code})
            comprehension = reading.get("readability", 0.0)
            learned = self.knowledge.learn_from_record(
                record, evd, comprehension, expertise_bonus=0.35)
            if learned:
                print(f"{consultant.name}辨认出的只是记录本身的主张：")
                self._print_learned_claims(learned, indent="  ")
            else:
                print("残留文字不足以组成可复述的主张。")
            return

        print(f"\n--- 向当地居民出示 {_evidence_display_name(evd)} ---")
        if date_range:
            print("居民只能判断它不像近期留下的东西。")
        if record is None:
            oral_carrier = self._find_related_oral_account(evd)
            if oral_carrier is None:
                print("没有人认出它对应哪段往事；几种猜测彼此矛盾。")
                return
            record = self.world.records.get(oral_carrier.source_record_id)
            if record is None:
                print("有人想起一段残缺说法，但已经无法连续复述。")
                return
            self.knowledge.discover_evidence(oral_carrier.id)
            learned = self.knowledge.learn_from_record(
                record, oral_carrier, comprehension=0.55)
            print("一位居民把这些痕迹与当地口述联系起来；这只是其所知版本：")
            self._print_learned_claims(learned, indent="  ")
            return
        learned = self.knowledge.learn_from_record(
            record, evd, comprehension=0.20, expertise_bonus=0.10)
        if learned:
            print("一位居民认出了其中流传过的说法，但提醒你当地版本并不统一：")
            self._print_learned_claims(learned, indent="  ")
        else:
            print("居民认得一些字形或纹样，却无法给出连续的解释。")


    def _find_related_oral_account(self, evidence):
        source_events = set(evidence.source_event_ids)
        if not source_events:
            return None
        candidates = [
            item for item in self.world.evidence.values()
            if item.location_id == self.current_location_id
            and item.evidence_type == "oral"
            and item.state != "destroyed"
            and item.source_record_id is not None
            and source_events.intersection(item.source_event_ids)
        ]
        return sorted(candidates, key=lambda item: item.id)[0] \
            if candidates else None


    def _find_local_consultant(self):
        roles = {"scholar", "scribe", "writer"}
        candidates = [
            person for person in self.world.persons.values()
            if person.alive and person.settlement_id == self.current_location_id
            and roles.intersection(person.roles)
        ]
        return sorted(candidates, key=lambda person: person.id)[0] \
            if candidates else None


    @staticmethod
    def _print_learned_claims(claims, indent=""):
        if not claims:
            return
        print(f"\n{indent}记入游记的主张：")
        for claim in claims:
            years = (str(claim.time_range[0])
                     if claim.time_range[0] == claim.time_range[1]
                     else f"{claim.time_range[0]}~{claim.time_range[1]}")
            print(f"{indent}- [{years}，{claim.status}] {claim.statement_cn}")


    def _resolve_local_evidence(self, target: str):
        """Resolve visible local evidence by list number or observed name."""
        evidence_list = self.world.get_all_visible_evidence(self.current_location_id)
        try:
            idx = int(target) - 1
            if 0 <= idx < len(evidence_list):
                return evidence_list[idx]
            print(f"编号超出范围，1~{len(evidence_list)} 之间。")
            return None
        except ValueError:
            matches = [
                evidence for evidence in evidence_list
                if (target.lower() in evidence.subtype.lower()
                    or target.lower() in _evidence_display_name(evidence).lower())
            ]
            if not matches:
                print(f"在这里找不到'{target}'。试试输入编号或者名字关键词。")
                return None
            return matches[0]


    def cmd_travel(self, destination: str):
        """前往指定地点。"""
        # 按名称搜索
        matches = []
        for stl in self.world.settlements.values():
            if destination.lower() in stl.name.lower():
                matches.append(stl)

        if not matches:
            print(f"没找到叫'{destination}'的地方。输入 locations 查看所有已知地点。")
            return

        if len(matches) > 1:
            print(f"找到多个匹配：")
            for s in matches:
                status = "废墟" if not s.alive else f"{s.size}"
                print(f"  {s.name} ({status})")
            print(f"请输入更精确的名称。")
            return

        print(f"正在前往{matches[0].name}……")
        self.travel_to(matches[0].id)


    def cmd_map(self):
        """显示世界概览。"""
        alive = [s for s in self.world.settlements.values() if s.alive]
        ruined = [s for s in self.world.settlements.values() if not s.alive]

        print(f"\n===== 已知地点 =====")
        if alive:
            print(f"\n现存聚落：")
            for s in alive:
                mark = " ← 你在这里" if s.id == self.current_location_id else ""
                print(f"  {s.name} — {s.size}, 人口{s.population} ({s.biome}){mark}")
        if ruined:
            print(f"\n废墟：")
            for s in ruined:
                mark = " ← 你在这里" if s.id == self.current_location_id else ""
                print(f"  {s.name} — 毁坏原因尚未查明 ({s.biome}){mark}")


    def cmd_journal(self):
        """显示游记笔记。"""
        print(f"\n===== 探险家游记 =====")
        print(f"当前年份：{self.world.current_year}")
        print(f"探访过的地方：{len(self.visited_locations)} 处")
        print(f"检查过的证据：{len(self.examined_evidence)} 件")
        print(f"读过的文书：{len(self.read_evidence)} 份")
        print(f"记录下来的历史主张：{len(self.knowledge.known_claims)} 条")

        if self.knowledge.known_claims:
            print(f"\n当前主张：")
            for claim in self.knowledge.sorted_claims():
                conflict = "，存在冲突材料" \
                    if claim.contradicting_evidence_ids else ""
                print(f"  [{claim.status}{conflict}] {claim.statement_cn}")


    def cmd_events(self):
        """List the player's claim-based reconstruction, not event truth."""
        print(f"\n===== 重建中的历史 =====")
        claims = self.knowledge.sorted_claims()
        if not claims:
            print("你还没有足够依据确认任何历史事件。")
            return

        for claim in claims:
            years = (str(claim.time_range[0])
                     if claim.time_range[0] == claim.time_range[1]
                     else f"{claim.time_range[0]}~{claim.time_range[1]}")
            conflict = "；有冲突" if claim.contradicting_evidence_ids else ""
            print(f"  [{years}] {claim.statement_cn} "
                  f"({claim.status}{conflict})")


    def cmd_locations(self):
        """列出所有地点。"""
        self.cmd_map()


    def cmd_search(self, query: str):
        """在已知知识中搜索。"""
        results = list(self.knowledge.search(query))

        for evidence_id in self.examined_evidence:
            evd = self.world.evidence.get(evidence_id)
            if evd is None:
                continue
            display_name = _evidence_display_name(evd)
            if (query.lower() in display_name.lower() or
                    query.lower() in evd.material.lower()):
                results.append(evd)

        if not results:
            print(f"没找到与'{query}'相关的内容。")
            return

        print(f"\n===== 搜索 '{query}' =====")
        for r in results[:10]:
            if hasattr(r, 'statement_cn'):
                print(f"  主张: {r.statement_cn} ({r.status})")
            elif hasattr(r, 'subtype'):  # Evidence
                print(f"  证据: {_evidence_display_name(r)} ({r.state})")


# ---- 显示辅助 ----

def _evidence_display_name(evidence) -> str:
    return evidence.physical_features.get(
        "display_name", evidence.subtype.replace("_", " "))


# ---- 入口 ----

def print_welcome(world: World):
    """打印欢迎信息。"""
    llm_status = "LLM 已就绪 ✓" if is_llm_available() else "模板模式（无 LLM）"
    print(f"""
╔══════════════════════════════════════════════════════╗
║              HistoryFinder — 历史寻踪                ║
║            程序生成世界的考古探险之旅                   ║
╠══════════════════════════════════════════════════════╣
║  Seed: {world.seed:<8}    年份: {world.current_year:<6}    聚落: {len(world.settlements):<3}     ║
║  状态: {llm_status:<42} ║
╠══════════════════════════════════════════════════════╣
║  你是一位探险家，踏上了这片未知的土地。                   ║
║  输入 help 查看指令，开始你的探索吧。                    ║
╚══════════════════════════════════════════════════════╝
""")


def print_help():
    """打印帮助信息。"""
    print("""
===== 可用指令 =====

导航与探索：
  look / l            重新观察当前地点
  travel to <地名>    前往指定地点
  locations / map     查看所有已知地点
  examine <编号/名字> 仔细检查一件证据
  read <编号/名字>    阅读已检查过的文书
  present <证物> to scholar/villager
                      向当地学者或居民出示证物
  search <关键词>     在游记和已检查证物中搜索

笔记：
  journal / j         查看游记（已知事件和证据）
  events / history    查看已确认的历史

系统：
  world info          查看世界基本信息
  cache clear         清空 LLM 缓存
  help                显示此帮助
  quit / exit         退出游戏

提示：在聚落中 look 之后，用编号 examine 证据最方便。
    """)
