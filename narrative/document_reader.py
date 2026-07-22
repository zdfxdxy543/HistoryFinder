"""Render only the portions of an in-world document a character can read."""

from __future__ import annotations

import hashlib
import re

from simulation.text_carriers import render_damaged_passages


STATE_READABILITY = {
    "intact": 1.0,
    "weathered": 0.65,
    "ruined": 0.3,
    "buried": 0.75,
}


def _tag_value(evidence, namespace: str, fallback: str = "") -> str:
    prefix = namespace + ":"
    for tag in evidence.physical_features.get("tags", []):
        if tag.startswith(prefix):
            return tag[len(prefix):]
    return fallback


def _stable_int(evidence_id: str, passage_index: int, salt: str) -> int:
    payload = f"{evidence_id}|{passage_index}|{salt}".encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest()[:16], 16)


def _clean_fragment(text: str) -> str:
    return text.strip(" ，。；：、！？‘’“”\t\n")


def _expand_ascii_word(text: str, start: int, end: int) -> tuple[int, int]:
    """Keep a surviving Latin-script name whole when a fragment touches it."""
    while start > 0 and text[start].isascii() and text[start].isalnum() \
            and text[start - 1].isascii() and text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end - 1].isascii() \
            and text[end - 1].isalnum() and text[end].isascii() \
            and text[end].isalnum():
        end += 1
    return start, end


def _isolated_fragments(text: str, evidence_id: str, passage_index: int,
                        readability: float) -> str:
    clean = _clean_fragment(text)
    if not clean:
        return "〔字迹全失〕"

    chunk_count = max(1, round(4 * readability))
    chunk_size = max(1, round(1 + 3 * readability))
    starts = []
    available = max(1, len(clean) - chunk_size + 1)
    for index in range(chunk_count * 2):
        start = _stable_int(evidence_id, passage_index, f"fragment-{index}") % available
        if all(abs(start - existing) >= chunk_size for existing in starts):
            starts.append(start)
        if len(starts) >= chunk_count:
            break
    if not starts:
        starts = [0]

    spans = [_expand_ascii_word(
        clean, start, min(len(clean), start + chunk_size))
        for start in sorted(starts)]
    fragments = [_clean_fragment(clean[start:end]) for start, end in spans]
    fragments = [fragment for fragment in fragments if fragment]
    return "……" + "……".join(fragments) + "……"


def _middle_fragment(text: str, readability: float) -> str:
    clean = _clean_fragment(text)
    if not clean:
        return "〔字迹全失〕"
    visible_length = max(2, round(len(clean) * (0.35 + 0.35 * readability)))
    start = max(0, (len(clean) - visible_length) // 2)
    end = min(len(clean), start + visible_length)
    return f"〔开头缺损〕{clean[start:end]}〔末尾缺损〕"


def _numbers_and_symbols(text: str, evidence_id: str, passage_index: int,
                         readability: float) -> str:
    visible = []
    threshold = int(10 + 25 * readability)
    for char_index, char in enumerate(text):
        keep = char.isdigit() or char in "年月日+-=×/" or char.isspace()
        if not keep and char not in "，。；：、！？‘’“”":
            keep = (_stable_int(
                evidence_id, passage_index, f"char-{char_index}") % 100) < threshold
        visible.append(char if keep else "□")
    masked = "".join(visible)
    masked = re.sub(r"□{2,}", "〔漫漶〕", masked)
    return masked.strip() or "〔字迹全失〕"


def _render_passage(text: str, mode: str, evidence_id: str,
                    passage_index: int, readability: float,
                    kind: str) -> str:
    if mode == "clear_large_letters":
        if readability >= 0.75:
            return text
        if readability >= 0.4:
            return _middle_fragment(text, readability)
        return _isolated_fragments(
            text, evidence_id, passage_index, readability)
    if mode == "missing_ends":
        return _middle_fragment(text, readability)
    if mode == "numbers_and_symbols":
        return _numbers_and_symbols(
            text, evidence_id, passage_index, readability)
    if mode == "seal_area_clear" and kind == "closing":
        if readability >= 0.5:
            return text
        return _middle_fragment(text, readability)
    return _isolated_fragments(text, evidence_id, passage_index, readability)


def read_document(evidence, known_languages: set[str]) -> dict:
    """Read words physically present on a carrier without consulting truth."""
    written = evidence.content_data.get("written_content")
    if not written:
        return {
            "status": "no_text",
            "text": "这件东西上没有可以连续阅读的书写内容。",
        }
    if evidence.state == "destroyed":
        return {
            "status": "destroyed",
            "text": "这件书写载体已经损毁，无法再读取。",
        }

    language_code = written.get("language_code", "unknown")
    language_name = written.get("language_name", language_code)
    if language_code not in known_languages:
        return {
            "status": "unknown_language",
            "language_code": language_code,
            "text": (
                f"载体表面仍有成列字符，但你不懂{language_name}，"
                "目前只能临摹字形，不能判断这些句子是什么意思。"
            ),
        }

    passages = written.get("passages", [])
    if (int(written.get("format_version", 1))
            >= 3 and evidence.content_data.get("text_layout")):
        mode = "persistent_damage_map"
        visible_passages, readability = render_damaged_passages(evidence)
    else:
        mode = _tag_value(evidence, "legibility", "isolated_glyphs")
        readability = STATE_READABILITY.get(evidence.state, 0.5)
        if evidence.max_durability > 0:
            durability_ratio = max(
                0.0, min(
                    1.0,
                    evidence.current_durability / evidence.max_durability))
            readability *= 0.5 + 0.5 * durability_ratio

        visible_passages = []
        for index, passage in enumerate(passages):
            text = passage.get("text", "")
            if not text:
                continue
            rendered = _render_passage(
                text, mode, evidence.id, index, readability,
                passage.get("kind", "body"))
            visible_passages.append(rendered)

    base_subtype = evidence.subtype.removesuffix("_copy") \
        if evidence.is_copy_of else evidence.subtype
    literary_work = base_subtype in {
        "literary_manuscript", "traveling_literary_copy",
    }
    literary_commentary = base_subtype == "literary_commentary"
    if not visible_passages:
        body = "墨迹已经无法组成可辨的句子。"
    elif literary_work or literary_commentary:
        body = "\n\n".join(visible_passages)
    else:
        body = "\n".join(f"  “{line}”" for line in visible_passages)

    if literary_work:
        rendered_text = (
            f"语言：{language_name}\n\n"
            f"作品正文（现存部分）：\n\n{body}"
        )
    elif literary_commentary:
        rendered_text = (
            f"语言：{language_name}\n\n"
            f"作品校注（现存部分）：\n\n{body}"
        )
    else:
        rendered_text = (
            f"语言：{language_name}\n\n"
            f"可辨文字：\n{body}"
        )
    return {
        "status": "readable",
        "language_code": language_code,
        "legibility": mode,
        "readability": readability,
        "visible_passages": visible_passages,
        "text": rendered_text,
    }


def is_public_inscription(evidence) -> bool:
    """Whether exposed large lettering can be approached as ordinary signage."""
    return "visibility:public_inscription" in evidence.physical_features.get(
        "tags", ()) and bool(evidence.content_data.get("written_content"))


def preview_public_inscription(evidence, known_languages: set[str]) -> dict | None:
    """Return only the immediately visible heading of a public inscription."""
    if not is_public_inscription(evidence):
        return None
    result = read_document(evidence, known_languages)
    preview = {
        "status": result.get("status", "no_text"),
        "language_code": result.get("language_code", "unknown"),
    }
    visible = result.get("visible_passages", ())
    if visible:
        preview["text"] = visible[0]
    elif result.get("status") == "unknown_language":
        preview["text"] = result.get("text", "")
    return preview
