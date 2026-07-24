"""
GameREPL：CLI 交互式探险 REPL。
从 main.py 拆出，不变更行为。
"""

import sys
from game.comparison import ComparisonEngine
from game.consultation import ConsultationEngine
from game.investigation import (
    ConsultantView,
    DocumentReading,
    EvidencePublicView,
    HeldKnowledgeView,
    ReadingPublicView,
    RecordPublicView,
    build_reading_statements,
)
from game.knowledge import PlayerKnowledge
from game.observation import build_evidence_observations
from simulation.world import World
from narrative.llm_interface import generate_narrative, is_llm_available, clear_cache
from narrative.document_reader import (
    is_public_inscription,
    preview_public_inscription,
    read_document,
)
from narrative.context_builder import (
    build_settlement_context,
    build_ruin_context,
    build_evidence_context,
    build_location_investigation_context,
)
from simulation.text_carriers import (
    has_text_carrier,
    materialize_text_carrier,
)


class GameREPL:
    """CLI 交互式探险 REPL。"""

    def __init__(self, world: World):
        self.world = world
        self.current_location_id: str | None = None  # 当前所在 settlement_id
        self.visited_locations: set[str] = set()
        self.known_events: set[str] = set()
        self.knowledge = PlayerKnowledge()
        # Compatibility aliases while investigation state moves into knowledge.
        self.examined_evidence = self.knowledge.examined_evidence_ids
        self.read_evidence = self.knowledge.read_evidence_ids
        self._consultation_engine = ConsultationEngine()
        self._comparison_engine = ComparisonEngine()
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

            elif cmd.startswith("journal "):
                self.cmd_journal(cmd[len("journal "):].strip())

            elif cmd.startswith("examine "):
                target = cmd[len("examine "):].strip()
                self.cmd_examine(target)

            elif cmd.startswith("read "):
                target = cmd[len("read "):].strip()
                self.cmd_read(target)

            elif cmd.startswith("present "):
                request = cmd[len("present "):].strip()
                self.cmd_present(request)

            elif cmd.startswith("compare "):
                request = cmd[len("compare "):].strip()
                self.cmd_compare(request)

            elif cmd.startswith("travel to "):
                dest = cmd[len("travel to "):].strip()
                self.cmd_travel(dest)

            elif cmd in ("travel", "go", "map"):
                self.cmd_map()

            elif cmd in ("events", "history"):
                self.cmd_events()

            elif cmd in ("locations", "settlements", "places"):
                self.cmd_locations()

            elif cmd in ("consultants", "people", "experts"):
                self.cmd_consultants()

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
                preview = preview_public_inscription(
                    evd, self.known_languages)
                if preview and preview.get("status") == "readable":
                    print(f"     醒目刻字：{preview.get('text', '字迹已损')}")


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

        evidence_view = EvidencePublicView.from_evidence(evd)
        observations = build_evidence_observations(evidence_view)
        self.knowledge.record_observations(evd.id, observations)


    def cmd_read(self, target: str):
        """阅读文书；公开碑铭不要求预先精细检查。"""
        if self.current_location_id is None:
            print("你还没有到达任何地方。先 travel 去一个聚落吧。")
            return

        evd = self._resolve_local_evidence(target)
        if evd is None:
            return
        if (evd.id not in self.examined_evidence
                and not is_public_inscription(evd)):
            print(f"你需要先 examine {_evidence_display_name(evd)}，确认它能否安全展开。")
            return

        if has_text_carrier(evd):
            evd = materialize_text_carrier(self.world, evd.id)
        result = read_document(evd, self.known_languages)
        print(f"\n--- 阅读 {_evidence_display_name(evd)} ---")
        print(result["text"])
        reading = DocumentReading.from_result(
            evd.id, self.current_location_id, result)
        statements = ()
        if result["status"] == "readable":
            record = self.world.records.get(evd.source_record_id)
            if record is not None:
                evidence_view = EvidencePublicView.from_evidence(evd)
                record_view = RecordPublicView.from_record_and_evidence(
                    record, evd)
                statements = build_reading_statements(
                    evidence_view, reading, record_view)
        learned = self.knowledge.record_reading(reading, statements)
        self._print_learned_claims(learned)


    def cmd_present(self, request: str):
        """Show examined evidence through the truth-isolated service."""
        if " to " not in request:
            print("用法：present <编号/名字> to <scholar/villager>")
            return
        target, audience = request.rsplit(" to ", 1)
        audience = audience.strip().lower()
        evd = self._resolve_local_evidence(target.strip())
        if evd is None:
            return
        if evd.id not in self.examined_evidence:
            print(f"你需要先 examine {_evidence_display_name(evd)}。")
            return

        informant = self._find_local_informant(audience)
        legacy_person = None
        if audience == "scholar":
            legacy_person = self._find_unregistered_scholar()
        if legacy_person is not None:
            consultant = ConsultantView.scholar(legacy_person)
            held_knowledge = ()
        elif informant is not None:
            person = self.world.persons.get(informant.person_id)
            if person is None or not person.alive:
                print("这位咨询者目前不在这里。")
                return
            consultant = ConsultantView.from_informant(informant, person)
            held_knowledge = self._informant_knowledge_views(informant)
        else:
            print(
                "这里找不到对应的咨询者。可使用 scholar、scribe、elder、"
                "villager、merchant、artisan，或输入当地咨询者的姓名。")
            return

        evidence_view = EvidencePublicView.from_evidence(evd)
        record_view = self._record_public_view(evd)
        reading_view = None
        if has_text_carrier(evd):
            evd = materialize_text_carrier(self.world, evd.id)
            reading = read_document(evd, set(consultant.known_languages))
            reading_view = ReadingPublicView.from_result(reading)

        result = self._consultation_engine.consult(
            evidence_view,
            consultant,
            reading=reading_view,
            record=record_view,
            held_knowledge=held_knowledge,
        )
        learned = self.knowledge.learn_from_consultation(result)

        print(f"\n--- 向{consultant.name}出示 {_evidence_display_name(evd)} ---")
        for note in result.notes_cn:
            print(note)
        for statement in result.statements:
            if statement.claim is None:
                print(statement.statement_cn)

        if learned and consultant.role in {"scholar", "scribe"}:
            print(f"{consultant.name}辨认出的只是记录本身的主张：")
            self._print_learned_claims(learned, indent="  ")
        elif learned:
            print(f"{consultant.name}强调，这只是其所知版本：")
            self._print_learned_claims(learned, indent="  ")
        elif result.claim_statements:
            print("这次复核没有为游记增加新的独立说法。")


    def cmd_compare(self, request: str):
        """Compare two examined local evidence items."""
        if " with " not in request:
            print("用法：compare <证物A> with <证物B>")
            return
        first_target, second_target = request.split(" with ", 1)
        first = self._resolve_local_evidence(first_target.strip())
        if first is None:
            return
        second = self._resolve_local_evidence(second_target.strip())
        if second is None:
            return
        if first.id == second.id:
            print("请选择两件不同的证物进行比较。")
            return
        missing = [
            item for item in (first, second)
            if item.id not in self.examined_evidence]
        if missing:
            names = "、".join(_evidence_display_name(item) for item in missing)
            print(f"需要先 examine {names}，留下可供比较的观察记录。")
            return

        first_observations = tuple(
            item for item in self.knowledge.observations.values()
            if item.evidence_id == first.id)
        second_observations = tuple(
            item for item in self.knowledge.observations.values()
            if item.evidence_id == second.id)
        result = self._comparison_engine.compare(
            EvidencePublicView.from_evidence(first),
            EvidencePublicView.from_evidence(second),
            first_observations,
            second_observations,
            self._source_groups_for_evidence(first.id),
            self._source_groups_for_evidence(second.id),
        )
        self.knowledge.record_comparison(result)

        print(
            f"\n--- 比较 {_evidence_display_name(first)} 与 "
            f"{_evidence_display_name(second)} ---")
        print("相同点：")
        for item in result.similarities_cn or ("没有记录到明确的共同特征。",):
            print(f"  {item}")
        print("差异点：")
        for item in result.differences_cn or ("没有记录到明确差异。",):
            print(f"  {item}")
        print("限制：")
        for item in result.limitations_cn:
            print(f"  {item}")


    def _source_groups_for_evidence(self, evidence_id: str) -> tuple[str, ...]:
        return tuple(sorted(
            group.id for group in self.knowledge.source_groups.values()
            if evidence_id in group.evidence_ids))


    def _record_public_view(self, evidence):
        record = self.world.records.get(evidence.source_record_id)
        if record is None:
            return None
        return RecordPublicView.from_record_and_evidence(record, evidence)


    def _informant_knowledge_views(
            self, informant) -> tuple[HeldKnowledgeView, ...]:
        views = []
        for entry in sorted(
                self.world.get_informant_knowledge(informant.id),
                key=lambda item: item.id):
            evidence = self.world.evidence.get(entry.source_evidence_id)
            record = self.world.records.get(entry.source_record_id)
            if evidence is None or record is None:
                continue
            view = HeldKnowledgeView.from_entry_record_and_evidence(
                entry, record, evidence)
            if view.record.claims:
                views.append(view)
        return tuple(views)


    def _find_local_informant(self, audience: str):
        aliases = {
            "villager": {"elder"},
            "elder": {"elder"},
            "scholar": {"scholar", "scribe"},
            "scribe": {"scribe"},
            "merchant": {"merchant"},
            "artisan": {"artisan"},
        }
        candidates = self.world.get_available_informants(
            self.current_location_id)
        normalized = audience.casefold()
        named = [
            informant for informant in candidates
            if self.world.persons[informant.person_id].name.casefold()
            == normalized
        ]
        if named:
            return named[0]
        roles = aliases.get(normalized)
        if roles is None:
            return None
        role_order = {
            role: index for index, role in enumerate(
                ("scholar", "scribe", "elder", "merchant", "artisan"))
        }
        matching = [
            informant for informant in candidates if informant.role in roles]
        return sorted(matching, key=lambda item: (
            role_order.get(item.role, 99), item.id))[0] if matching else None


    def _find_unregistered_scholar(self):
        roles = {"scholar", "scribe", "writer"}
        registered = {
            informant.person_id for informant in self.world.informants.values()
        }
        candidates = [
            person for person in self.world.persons.values()
            if person.alive
            and person.current_location_id == self.current_location_id
            and person.id not in registered
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


    def cmd_journal(self, section: str | None = None):
        """Display the investigation log, optionally filtered by category."""
        aliases = {
            "observations": "observations", "observation": "observations",
            "texts": "texts", "text": "texts", "documents": "texts",
            "statements": "statements", "statement": "statements",
            "claims": "claims", "claim": "claims",
            "conflicts": "conflicts", "conflict": "conflicts",
            "comparisons": "comparisons", "comparison": "comparisons",
        }
        selected = aliases.get(section, section) if section else None
        valid = {
            "observations", "texts", "statements", "claims", "conflicts",
            "comparisons"}
        if selected is not None and selected not in valid:
            print(
                "可查看：observations / texts / statements / claims / "
                "conflicts / comparisons")
            return

        print(f"\n===== 探险家游记 =====")
        print(f"当前年份：{self.world.current_year}")
        print(f"探访过的地方：{len(self.visited_locations)} 处")
        print(f"检查过的证据：{len(self.examined_evidence)} 件")
        print(f"读过的文书：{len(self.read_evidence)} 份")
        print(f"客观观察：{len(self.knowledge.observations)} 条")
        print(f"有来源的说法：{len(self.knowledge.source_statements)} 条")
        print(f"独立来源组：{len(self.knowledge.source_groups)} 组")
        print(f"证物比较：{len(self.knowledge.comparisons)} 次")
        print(f"记录下来的历史主张：{len(self.knowledge.known_claims)} 条")

        sections = (selected,) if selected else (
            "observations", "texts", "statements", "claims", "conflicts",
            "comparisons")
        if "observations" in sections:
            print("\n--- 客观观察 ---")
            observations = sorted(
                self.knowledge.observations.values(),
                key=lambda item: (item.evidence_id, item.id))
            if not observations:
                print("  尚无记录。")
            for observation in observations:
                print(
                    f"  [{self._evidence_name(observation.evidence_id)}] "
                    f"{observation.description_cn}"
                    f"（清晰度 {observation.clarity:.0%}）")

        if "texts" in sections:
            print("\n--- 文书原文 ---")
            readings = sorted(
                self.knowledge.document_readings.values(),
                key=lambda item: (item.evidence_id, item.id))
            if not readings:
                print("  尚无记录。")
            for reading in readings:
                name = self._evidence_name(reading.evidence_id)
                if not reading.visible_passages:
                    print(f"  [{name}] 未取得可辨原文（{reading.status}）。")
                    continue
                print(f"  [{name}] 语言 {reading.language_code}：")
                for passage in reading.visible_passages:
                    print(f"    “{passage}”")

        if "statements" in sections:
            print("\n--- 他人说法 ---")
            statements = sorted(
                (item for item in self.knowledge.source_statements.values()
                 if item.speaker_type != "player_reading"),
                key=lambda item: item.id)
            if not statements:
                print("  尚无记录。")
            for statement in statements:
                print(f"  {statement.statement_cn}")

        if "claims" in sections:
            print("\n--- 综合主张 ---")
            if not self.knowledge.known_claims:
                print("  尚无记录。")
            for claim in self.knowledge.sorted_claims():
                conflict = "，存在冲突材料" \
                    if claim.contradicting_evidence_ids else ""
                print(
                    f"  [{claim.status}{conflict}，"
                    f"{len(claim.source_groups)} 个独立来源组] "
                    f"{claim.statement_cn}")
                components = self._confidence_component_summary(claim)
                if components:
                    print(f"    置信度依据：{components}")

        if "conflicts" in sections:
            print("\n--- 未解决冲突 ---")
            conflicts = sorted(
                self.knowledge.conflicts.values(), key=lambda item: item.id)
            if not conflicts:
                print("  尚无记录。")
            for conflict in conflicts:
                first = self.knowledge.known_claims.get(
                    conflict.first_claim_key)
                second = self.knowledge.known_claims.get(
                    conflict.second_claim_key)
                first_text = (first.statement_cn if first is not None
                              else conflict.first_claim_key)
                second_text = (second.statement_cn if second is not None
                               else conflict.second_claim_key)
                print(
                    f"  [第{conflict.overlap_range[0]}~"
                    f"{conflict.overlap_range[1]}年] "
                    f"{first_text} / {second_text}")
                print(f"    {conflict.reason_cn}")

        if "comparisons" in sections:
            print("\n--- 证物比较 ---")
            comparisons = sorted(
                self.knowledge.comparisons.values(), key=lambda item: item.id)
            if not comparisons:
                print("  尚无记录。")
            for comparison in comparisons:
                first_id, second_id = comparison.evidence_ids
                print(
                    f"  {self._evidence_name(first_id)} / "
                    f"{self._evidence_name(second_id)}："
                    f"{len(comparison.similarities_cn)} 项相同，"
                    f"{len(comparison.differences_cn)} 项不同，"
                    f"来源关系 {comparison.source_group_relation}")


    def _evidence_name(self, evidence_id: str) -> str:
        evidence = self.world.evidence.get(evidence_id)
        return (_evidence_display_name(evidence)
                if evidence is not None else evidence_id)


    @staticmethod
    def _confidence_component_summary(claim) -> str:
        labels = {
            "carrier_quality": "载体质量",
            "directness": "直接程度",
            "expertise_match": "专业匹配",
            "comprehension": "文字理解",
            "temporal_proximity": "年代接近",
            "source_independence": "来源独立",
            "corroboration": "跨类型印证",
            "contradiction": "互斥冲突",
            "bias_penalty": "立场偏差",
            "transmission_penalty": "传承损耗",
        }
        parts = []
        for key, value in claim.confidence_components.items():
            if abs(value) < 0.0005:
                continue
            parts.append(f"{labels.get(key, key)} {value:+.0%}")
        return "，".join(parts)


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


    def cmd_consultants(self):
        """List living, persistent informants at the current location."""
        if self.current_location_id is None:
            print("你还没有到达任何聚落。")
            return
        informants = self.world.get_available_informants(
            self.current_location_id)
        if not informants:
            print("这里目前没有可以请教的人。")
            return
        role_names = {
            "scholar": "学者",
            "scribe": "书记",
            "elder": "地方长者",
            "merchant": "商人",
            "artisan": "工匠",
            "priest": "仪式保管人",
        }
        print("\n===== 当地咨询者 =====")
        for informant in informants:
            person = self.world.persons[informant.person_id]
            entries = len(informant.known_entry_ids)
            print(
                f"  {person.name} — {role_names.get(informant.role, informant.role)}"
                f"，掌握 {entries} 条有来源的知识")


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
  consultants         查看当地可咨询的人及其身份
  examine <编号/名字> 仔细检查一件证据
  read <编号/名字>    阅读已检查过的文书
  present <证物> to <咨询者>
                      可选 scholar/scribe/elder/villager/merchant/artisan 或姓名
  compare <A> with <B> 比较两件已检查证物
  search <关键词>     在游记和已检查证物中搜索

笔记：
  journal / j         分类查看调查日志
  journal <分类>      observations/texts/statements/claims/conflicts/comparisons
  events / history    查看已确认的历史

系统：
  world info          查看世界基本信息
  cache clear         清空 LLM 缓存
  help                显示此帮助
  quit / exit         退出游戏

提示：在聚落中 look 之后，用编号 examine 证据最方便。
    """)
