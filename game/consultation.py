"""Deterministic evidence consultation without access to historical truth."""

from __future__ import annotations

from collections.abc import Iterable

from game.investigation import (
    ClaimView,
    ConsultantView,
    ConsultationResult,
    EvidencePublicView,
    HeldKnowledgeView,
    OralKnowledgeView,
    ReadingPublicView,
    RecordPublicView,
    SourceStatement,
    source_group_id,
    stable_investigation_id,
)


class ConsultationEngine:
    """Interpret public evidence and source views, never simulation events."""

    def consult(self, evidence: EvidencePublicView,
                consultant: ConsultantView,
                reading: ReadingPublicView | None = None,
                record: RecordPublicView | None = None,
                held_knowledge: Iterable[HeldKnowledgeView] = (),
                oral_knowledge: Iterable[OralKnowledgeView] = (),
                question: str = "general") -> ConsultationResult:
        held_knowledge = tuple(held_knowledge)
        oral_knowledge = tuple(oral_knowledge)
        reading_signature = (
            f"{reading.status}:{reading.language_code}:"
            f"{reading.readability:.6f}"
            if reading is not None else "no-reading")
        knowledge_signature = ",".join(sorted(
            [item.entry_id for item in held_knowledge]
            + [item.evidence_id for item in oral_knowledge]))
        consultation_id = stable_investigation_id(
            "consultation",
            (
                consultant.id,
                evidence.id,
                evidence.state,
                f"{evidence.condition:.6f}",
                reading_signature,
                record.id if record is not None else "no-record",
                knowledge_signature,
                question,
            ),
        )
        if consultant.role in {"scholar", "scribe"}:
            return self._consult_scholar(
                consultation_id, evidence, consultant, reading, record,
                held_knowledge)
        if consultant.role in {"villager", "elder"}:
            return self._consult_local_community(
                consultation_id, evidence, consultant, reading, record,
                held_knowledge, oral_knowledge)
        return self._consult_specialist(
            consultation_id, evidence, consultant, reading, record,
            held_knowledge)

    def _consult_scholar(self, consultation_id: str,
                         evidence: EvidencePublicView,
                         consultant: ConsultantView,
                         reading: ReadingPublicView | None,
                         record: RecordPublicView | None,
                         held_knowledge: tuple[HeldKnowledgeView, ...],
                         ) -> ConsultationResult:
        notes = [self._scholar_observation(evidence, consultant)]
        statements: list[SourceStatement] = []

        if evidence.evidence_type != "document" or record is None:
            matched = self._match_held_knowledge(evidence, held_knowledge)
            if matched is not None and matched.record.claims:
                claim = matched.record.claims[0]
                statements.append(self._claim_statement(
                    consultation_id, 1, consultant, evidence,
                    source_evidence_id=matched.source_evidence_id,
                    record=matched.record,
                    claim=claim,
                    statement_type="scholarly_recollection",
                    statement_cn=(
                        f"{consultant.name}想起一份相关记录曾声称："
                        f"{claim.statement_cn}"
                    ),
                    basis_codes=("held_record", "shared_subject_domain"),
                    uncertainty_codes=("association_not_identity",),
                    condition=matched.certainty,
                    comprehension=max(0.25, matched.certainty * 0.75),
                    expertise_bonus=min(
                        0.30, self._relevant_expertise(
                            consultant, evidence) * 0.40),
                    transmission_depth=matched.transmission_depth,
                ))
                return self._result(
                    consultation_id, consultant, evidence, statements, notes,
                    matched_knowledge_ids=(matched.entry_id,))
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="limitation",
                statement_cn=(
                    f"{consultant.name}只能确认这些可见的材料和加工痕迹，"
                    "还不能把它归到某一段具体历史。"
                ),
                basis_codes=("physical_features_only",),
                uncertainty_codes=("no_readable_record",),
            ))
            return self._result(
                consultation_id, consultant, evidence, statements, notes)

        if reading is None or reading.status != "readable":
            reason = (
                "文字所用语言不在其掌握范围内"
                if reading and reading.status == "unknown_language"
                else "残留文字不足以连续辨认"
            )
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="limitation",
                statement_cn=f"{consultant.name}表示{reason}，不能复述其中的主张。",
                basis_codes=("document_condition",),
                uncertainty_codes=("unreadable_text",),
            ))
            return self._result(
                consultation_id, consultant, evidence, statements, notes)

        expertise = self._relevant_expertise(consultant, evidence)
        if not record.claims:
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="limitation",
                statement_cn="可辨文字没有保留下足以组成完整主张的部分。",
                basis_codes=("retained_text",),
                uncertainty_codes=("claim_not_retained",),
            ))
        else:
            for index, claim in enumerate(record.claims, 1):
                statements.append(self._claim_statement(
                    consultation_id, index, consultant, evidence,
                    source_evidence_id=evidence.id,
                    record=record,
                    claim=claim,
                    statement_type="transcription",
                    statement_cn=(
                        f"{consultant.name}辨认出文书中的一项说法："
                        f"{claim.statement_cn}"
                    ),
                    basis_codes=("readable_text", "retained_claim"),
                    uncertainty_codes=("record_claim_not_truth",),
                    condition=evidence.condition,
                    comprehension=reading.readability,
                    expertise_bonus=min(0.35, expertise * 0.45),
                ))

        return self._result(
            consultation_id, consultant, evidence, statements, notes)

    def _consult_local_community(
            self, consultation_id: str, evidence: EvidencePublicView,
            consultant: ConsultantView,
            reading: ReadingPublicView | None,
            record: RecordPublicView | None,
            held_knowledge: tuple[HeldKnowledgeView, ...],
            oral_knowledge: tuple[OralKnowledgeView, ...],
            ) -> ConsultationResult:
        notes: list[str] = []
        statements: list[SourceStatement] = []

        if (evidence.evidence_type == "document" and record is not None
                and reading is not None and reading.status == "readable"):
            notes.append(
                "居民只认出其中较常见的字句，并提醒你当地人的转述并不统一。")
            for index, claim in enumerate(record.claims[:1], 1):
                statements.append(self._claim_statement(
                    consultation_id, index, consultant, evidence,
                    source_evidence_id=evidence.id,
                    record=record,
                    claim=claim,
                    statement_type="partial_reading",
                    statement_cn=f"一位居民认出的文书说法是：{claim.statement_cn}",
                    basis_codes=("common_words", "retained_claim"),
                    uncertainty_codes=("limited_comprehension",),
                    condition=evidence.condition,
                    comprehension=min(0.35, reading.readability),
                    expertise_bonus=0.05,
                ))
            if not record.claims:
                notes.append("残留文字不足以组成可复述的说法。")
            return self._result(
                consultation_id, consultant, evidence, statements, notes)

        matched_held = self._match_held_knowledge(
            evidence,
            tuple(item for item in held_knowledge
                  if item.entry_type == "oral_account"),
        )
        if matched_held is not None:
            notes.append(
                f"{consultant.name}把这些可见痕迹与自己确实听过的一则说法联系起来；"
                "这种联系只依据题材和本地记忆，不能确认两者来自同一件事。")
            for index, claim in enumerate(
                    matched_held.record.claims[:1], 1):
                statements.append(self._claim_statement(
                    consultation_id, index, consultant, evidence,
                    source_evidence_id=matched_held.source_evidence_id,
                    record=matched_held.record,
                    claim=claim,
                    statement_type="oral_claim",
                    statement_cn=(
                        f"{consultant.name}记得的一个版本是："
                        f"{claim.statement_cn}"
                    ),
                    basis_codes=(
                        "held_oral_memory", "shared_subject_domain"),
                    uncertainty_codes=(
                        "oral_transmission", "association_not_identity"),
                    condition=matched_held.certainty,
                    comprehension=max(0.20, matched_held.certainty * 0.75),
                    expertise_bonus=0.0,
                    transmission_depth=matched_held.transmission_depth,
                ))
            return self._result(
                consultation_id, consultant, evidence, statements, notes,
                matched_knowledge_ids=(matched_held.entry_id,))

        matched = self._match_oral_knowledge(evidence, oral_knowledge)
        if matched is None:
            notes.append(
                "没有居民能把这些可见痕迹与自己确实听过的说法联系起来；"
                "现场出现的几种猜测都没有可追溯来源。")
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="limitation",
                statement_cn="当地居民无法为这件东西提供有来源的解释。",
                basis_codes=("local_memory_search",),
                uncertainty_codes=("no_matching_knowledge",),
            ))
            return self._result(
                consultation_id, consultant, evidence, statements, notes)

        notes.append(
            "一位居民把这些可见痕迹与当地流传的一则说法联系起来；"
            "这种联系只依据题材和本地记忆，不能确认两者来自同一件事。")
        for index, claim in enumerate(matched.record.claims[:1], 1):
            statements.append(self._claim_statement(
                consultation_id, index, consultant, evidence,
                source_evidence_id=matched.evidence_id,
                record=matched.record,
                claim=claim,
                statement_type="oral_claim",
                statement_cn=f"当地口述的一种版本是：{claim.statement_cn}",
                basis_codes=("local_oral_memory", "shared_subject_domain"),
                uncertainty_codes=(
                    "oral_transmission", "association_not_identity"),
                condition=matched.condition,
                comprehension=0.55,
                expertise_bonus=0.0,
                transmission_depth=1,
            ))
        return self._result(
            consultation_id, consultant, evidence, statements, notes,
            matched_knowledge_ids=(matched.evidence_id,))

    def _consult_specialist(
            self, consultation_id: str, evidence: EvidencePublicView,
            consultant: ConsultantView,
            reading: ReadingPublicView | None,
            record: RecordPublicView | None,
            held_knowledge: tuple[HeldKnowledgeView, ...],
            ) -> ConsultationResult:
        role_names = {"merchant": "商旅与账目", "artisan": "材料与工艺"}
        expertise = self._relevant_expertise(consultant, evidence)
        notes = [
            f"{consultant.name}只从自己熟悉的{role_names.get(consultant.role, '领域')}"
            "检查这件材料，不对陌生部分作判断。"
        ]
        statements: list[SourceStatement] = []

        if consultant.role == "artisan":
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="professional_observation",
                statement_cn=(
                    f"{consultant.name}可以讨论材质、接合和磨损，"
                    "但这些痕迹本身不能说明物品经历过哪件历史事件。"
                ),
                basis_codes=("material", "surface_marks"),
                uncertainty_codes=("purpose_unknown",),
                expertise_bonus=min(0.30, expertise * 0.35),
            ))
        elif consultant.role == "merchant":
            statements.append(self._statement(
                consultation_id, 1, consultant, evidence,
                statement_type="professional_observation",
                statement_cn=(
                    f"{consultant.name}只能比较形制、记号和账目习惯，"
                    "不能仅凭相似之处确定货物来自何处。"
                ),
                basis_codes=("trade_forms", "marks"),
                uncertainty_codes=("origin_unknown",),
                expertise_bonus=min(0.30, expertise * 0.35),
            ))

        matched = self._match_held_knowledge(evidence, held_knowledge)
        if matched is not None and matched.record.claims:
            claim = matched.record.claims[0]
            statements.append(self._claim_statement(
                consultation_id, len(statements) + 1,
                consultant, evidence,
                source_evidence_id=matched.source_evidence_id,
                record=matched.record,
                claim=claim,
                statement_type="professional_recollection",
                statement_cn=(
                    f"{consultant.name}记得自己接触过的一份材料声称："
                    f"{claim.statement_cn}"
                ),
                basis_codes=("held_record", "professional_domain"),
                uncertainty_codes=("association_not_identity",),
                condition=matched.certainty,
                comprehension=max(0.20, matched.certainty * 0.70),
                expertise_bonus=min(0.25, expertise * 0.35),
                transmission_depth=matched.transmission_depth,
            ))
            return self._result(
                consultation_id, consultant, evidence, statements, notes,
                matched_knowledge_ids=(matched.entry_id,))

        notes.append("他没有持有能与这件材料可靠对照的记录或口述来源。")
        return self._result(
            consultation_id, consultant, evidence, statements, notes)

    @staticmethod
    def _match_held_knowledge(
            evidence: EvidencePublicView,
            held_knowledge: tuple[HeldKnowledgeView, ...],
            ) -> HeldKnowledgeView | None:
        evidence_domains = set(evidence.analysis_domains)
        ranked = []
        for knowledge in held_knowledge:
            if not knowledge.record.claims:
                continue
            shared = evidence_domains.intersection(knowledge.domains)
            specific = shared - {"local_history"}
            if not shared:
                continue
            local = evidence.location_id in knowledge.location_ids
            score = (
                len(specific) * 10 + len(shared)
                + (2 if local else 0)
                + knowledge.certainty
                - knowledge.transmission_depth * 0.25
            )
            ranked.append((-score, knowledge.entry_id, knowledge))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][2]

    @staticmethod
    def _match_oral_knowledge(
            evidence: EvidencePublicView,
            oral_knowledge: tuple[OralKnowledgeView, ...],
            ) -> OralKnowledgeView | None:
        evidence_domains = set(evidence.analysis_domains)
        ranked = []
        for knowledge in oral_knowledge:
            if knowledge.location_id != evidence.location_id:
                continue
            shared = evidence_domains.intersection(knowledge.domains)
            specific = shared - {"local_history"}
            if not shared:
                continue
            score = len(specific) * 10 + len(shared) + knowledge.condition
            ranked.append((-score, knowledge.evidence_id, knowledge))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][2]

    @staticmethod
    def _scholar_observation(evidence: EvidencePublicView,
                             consultant: ConsultantView) -> str:
        if evidence.evidence_type == "document":
            return (
                f"{consultant.name}先区分了载体、字迹和文字内容；"
                "仅凭外观不能断定文书所写内容是否真实。"
            )
        return (
            f"{consultant.name}检查了材质、表面和残损位置；"
            "这些观察能够帮助分类，但不能单独确定历史归属。"
        )

    @staticmethod
    def _relevant_expertise(consultant: ConsultantView,
                            evidence: EvidencePublicView) -> float:
        return max(
            (consultant.expertise_for(domain)
             for domain in evidence.analysis_domains),
            default=0.0,
        )

    @staticmethod
    def _statement(consultation_id: str, index: int,
                   consultant: ConsultantView,
                   evidence: EvidencePublicView, **kwargs) -> SourceStatement:
        return SourceStatement(
            id=stable_investigation_id(
                "statement", (consultation_id, str(index))),
            speaker_type=("community" if consultant.role == "villager"
                          else "informant"),
            speaker_id=consultant.id,
            presented_evidence_id=evidence.id,
            source_evidence_id=None,
            source_record_root_id=None,
            **kwargs,
        )

    @staticmethod
    def _claim_statement(
            consultation_id: str, index: int,
            consultant: ConsultantView, evidence: EvidencePublicView,
            source_evidence_id: str, record: RecordPublicView,
            claim: ClaimView, statement_type: str, statement_cn: str,
            basis_codes: tuple[str, ...],
            uncertainty_codes: tuple[str, ...], condition: float,
            comprehension: float, expertise_bonus: float,
            transmission_depth: int | None = None,
            ) -> SourceStatement:
        return SourceStatement(
            id=stable_investigation_id(
                "statement", (consultation_id, str(index))),
            speaker_type=("community" if consultant.role == "villager"
                          else "informant"),
            speaker_id=consultant.id,
            presented_evidence_id=evidence.id,
            source_evidence_id=source_evidence_id,
            source_record_root_id=record.source_root_id,
            statement_type=statement_type,
            statement_cn=statement_cn,
            basis_codes=basis_codes,
            uncertainty_codes=uncertainty_codes,
            claim=claim,
            perspective=record.perspective,
            carrier_condition=condition,
            comprehension=comprehension,
            expertise_bonus=expertise_bonus,
            source_group_id=(record.source_group_id
                             or source_group_id(record.source_root_id)),
            source_group_type=(
                "oral_tradition"
                if record.record_type == "oral_tradition"
                else "record_lineage"),
            transmission_depth=(
                max(0, transmission_depth)
                if transmission_depth is not None
                else (1 if record.id != record.source_root_id else 0)),
        )

    @staticmethod
    def _result(consultation_id: str, consultant: ConsultantView,
                evidence: EvidencePublicView,
                statements: list[SourceStatement], notes: list[str],
                matched_knowledge_ids: tuple[str, ...] = (),
                ) -> ConsultationResult:
        return ConsultationResult(
            id=consultation_id,
            consultant_id=consultant.id,
            consultant_name=consultant.name,
            consultant_role=consultant.role,
            evidence_id=evidence.id,
            statements=tuple(statements),
            notes_cn=tuple(notes),
            matched_knowledge_ids=matched_knowledge_ids,
        )
