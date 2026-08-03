"""Shared public document identity for holdings and historical carriers."""

from __future__ import annotations

from dataclasses import dataclass

from simulation.text_carriers import DAMAGE_LABELS as CARRIER_DAMAGE_LABELS


DOCUMENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DocumentProfile:
    id: str
    document_kind: str
    title: str
    author_name: str
    date_label: str
    origin_name: str
    language_code: str
    form: str
    material: str
    condition: str
    registered: bool
    read: bool
    schema_version: int = DOCUMENT_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "document_kind": self.document_kind,
            "title": self.title,
            "author_name": self.author_name,
            "date_label": self.date_label,
            "origin_name": self.origin_name,
            "language_code": self.language_code,
            "form": self.form,
            "material": self.material,
            "condition": self.condition,
            "registered": self.registered,
            "read": self.read,
        }

    @classmethod
    def from_library_book(
            cls, book, *, registered: bool = False,
            read: bool = False) -> "DocumentProfile":
        return cls(
            id=book.id,
            document_kind="ordinary_holding",
            title=book.title,
            author_name=book.author_name,
            date_label=f"第 {int(book.created_year)} 年",
            origin_name=book.origin_name,
            language_code=book.language_code,
            form=str(book.text_plan.get("form", "馆藏文献")),
            material="paper",
            condition=book.condition,
            registered=registered,
            read=read,
        )

    @classmethod
    def from_historical_evidence(
            cls, evidence, *, registered: bool = True,
            read: bool = False) -> "DocumentProfile":
        written = evidence.content_data.get("written_content", {})
        passages = list(written.get("passages", ()))
        heading = next((
            str(item.get("text", "")) for item in passages
            if item.get("kind") == "heading" and item.get("text")
        ), "")
        display_name = str(evidence.physical_features.get(
            "display_name", evidence.subtype.replace("_", " ")))
        author = str(
            written.get("author_name")
            or evidence.content_data.get("author_name")
            or "作者未署名"
        )
        language = str(
            written.get("language_code")
            or evidence.content_data.get("language", "common")
        )
        return cls(
            id=evidence.id,
            document_kind="historical_source",
            title=heading or display_name,
            author_name=author,
            date_label="年代待考",
            origin_name=str(
                evidence.provenance_clues.get("origin_name")
                or evidence.origin_location_id
                or evidence.location_id
            ),
            language_code=language,
            form=evidence.subtype.removesuffix("_copy").replace("_", " "),
            material=evidence.material,
            condition=evidence.state,
            registered=registered,
            read=read,
        )


def historical_damage_labels(evidence) -> list[str]:
    """Return stable public damage labels without exposing lesion geometry."""
    labels = []
    for lesion in evidence.content_data.get(
            "damage_state", {}).get("lesions", ()):
        label = CARRIER_DAMAGE_LABELS.get(
            str(lesion.get("damage_type", "")), "此处缺损")
        if label not in labels:
            labels.append(label)
    return labels
