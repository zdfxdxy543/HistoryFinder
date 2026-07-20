"""
LLM 接口：封装 llama-cpp-python，提供叙事生成与降级方案。
Phase 1: 基础实现 + 模板 fallback。
"""

import os
import hashlib
import json
import threading
from typing import Optional

from narrative.prompt_templates import (
    VOICE_SYSTEM_PROMPTS,
    QUERY_TEMPLATES,
)
from narrative.evidence_describer import describe_evidence

# ---- LLM 加载 ----

_llm_instance = None
_llm_available = False


def init_llm(model_path: str, n_ctx: int = 4096, n_threads: int = 8) -> bool:
    """
    尝试加载本地 LLM。成功返回 True，失败返回 False。
    失败时不崩溃——游戏可以降级到模板模式。
    """
    global _llm_instance, _llm_available

    if not os.path.exists(model_path):
        print(f"[LLM] 模型文件未找到: {model_path}")
        print("[LLM] 将使用模板降级模式。")
        _llm_available = False
        return False

    try:
        from llama_cpp import Llama
        _llm_instance = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
        )
        _llm_available = True
        print(f"[LLM] 模型加载成功: {model_path}")
        return True
    except ImportError:
        print("[LLM] llama-cpp-python 未安装。将使用模板降级模式。")
        print("[LLM] 安装方法: pip install llama-cpp-python")
        _llm_available = False
        return False
    except Exception as e:
        print(f"[LLM] 模型加载失败: {e}")
        print("[LLM] 将使用模板降级模式。")
        _llm_available = False
        return False


def is_llm_available() -> bool:
    return _llm_available


# ---- 叙事生成 ----

_generation_lock = threading.Lock()
# 简易内存缓存
_cache: dict[str, str] = {}


def generate_narrative(
    voice: str,
    query_type: str,
    context: dict,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> str:
    """
    生成一段叙事文本。
    voice: 叙事声音 key（参见 prompt_templates.py）
    query_type: 查询类型 key
    context: 上下文数据 dict
    """
    # 计算缓存 key
    cache_key = _compute_cache_key(voice, query_type, context)
    if cache_key in _cache:
        return _cache[cache_key]

    # 构建 prompt
    system_prompt = VOICE_SYSTEM_PROMPTS.get(voice, VOICE_SYSTEM_PROMPTS["neutral_narrative"])
    # 如果有占位符（如 npc_personal），替换之
    system_prompt = system_prompt.format(**context) if "{" in system_prompt else system_prompt

    query_template = QUERY_TEMPLATES.get(query_type, "")
    user_query = query_template.format(**context) if query_template else str(context)

    # 如果有 LLM，使用 LLM
    if _llm_available and _llm_instance is not None:
        result = _generate_with_llm(system_prompt, user_query, max_tokens, temperature)
    else:
        result = _generate_with_template(voice, query_type, context)

    _cache[cache_key] = result
    return result


def _generate_with_llm(system_prompt: str, user_query: str,
                        max_tokens: int, temperature: float) -> str:
    """使用本地 LLM 生成。"""
    global _llm_instance

    prompt = f"""<|system|>
{system_prompt}
</s>
<|user|>
{user_query}
</s>
<|assistant|>"""

    with _generation_lock:
        try:
            result = _llm_instance(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=0.9,
                stop=["</s>", "<|user|>", "<|system|>"],
                echo=False,
            )
            text = result['choices'][0]['text'].strip()
            return text if text else _generate_with_template("neutral_narrative", "", {})
        except Exception as e:
            print(f"[LLM] 生成失败: {e}，降级到模板。")
            return _generate_with_template("neutral_narrative", "", {})


def _generate_with_template(voice: str, query_type: str, context: dict) -> str:
    """
    模板降级方案：用结构化数据直接拼文字。
    虽然不够文学化，但保证游戏能跑。
    """
    if query_type == "arrive_at_settlement":
        return _template_arrive_settlement(context)
    elif query_type == "arrive_at_ruin":
        return _template_arrive_ruin(context)
    elif query_type == "examine_evidence":
        return _template_examine_evidence(context)
    elif query_type == "examine_location":
        return _template_examine_location(context)
    else:
        return _template_examine_location(context)


# ---- 模板方法 ----

def _template_arrive_settlement(ctx: dict) -> str:
    name = ctx.get("settlement_name", "Unknown")
    size = ctx.get("settlement_size", "settlement")
    biome = ctx.get("biome", "unknown lands")
    pop = ctx.get("population", 0)
    ruler = ctx.get("ruler_name", "")
    alive = ctx.get("alive", True)
    evidence = ctx.get("evidence_summary", "")

    if alive:
        size_cn = {"village": "村庄", "town": "城镇", "city": "城市"}.get(size, size)
        text = (
            f"你来到了{name}，一座坐落在{biome}之中的{size_cn}。\n\n"
            f"聚落中如今约有{pop}名居民。"
        )
        if ruler:
            text += f" 现任领主是{ruler}。"
        text += "\n\n"
        if evidence and evidence != "No visible evidence found here.":
            text += f"你注意到附近有一些值得调查的东西：\n{evidence}"
    else:
        text = _template_arrive_ruin(ctx)

    return text


def _template_arrive_ruin(ctx: dict) -> str:
    name = ctx.get("settlement_name", "Unknown")
    biome = ctx.get("biome", "the wilds")
    evidence = ctx.get("evidence_summary", "")

    text = (
        f"你站在{name}的废墟前。\n\n"
        f"如今，{biome}正在慢慢覆盖这里裸露的墙基和倒塌构件。"
        f"野草从石缝中钻出，部分石块仍保持排列，另一些已经散落进土层。\n\n"
        f"从眼前的遗存还无法判断这里在何时、因为什么被废弃。"
    )

    if evidence and evidence != "No visible evidence found here.":
        text += f"\n\n残存的可调查痕迹：\n{evidence}"

    return text


def _template_examine_evidence(ctx: dict) -> str:
    return describe_evidence(ctx)


def _template_examine_location(ctx: dict) -> str:
    name = ctx.get("location_name", "this place")
    ltype = ctx.get("location_type", "area")
    biome = ctx.get("biome", "")
    evidence = ctx.get("evidence_summary", "")

    text = f"你花了些时间在{name}四处探查。\n\n"
    text += f"这里的{biome}地貌中"
    if ltype == "ruin":
        text += "，到处散落着废墟的残片。倒塌的石柱、破碎的陶片、被烧过的木梁——每一件都在无声地讲述过去。"
    elif ltype in ("wilderness",):
        text += "，并没有太多人类活动的痕迹。不过，仔细搜寻之下，仍然有一些值得注意的发现。"
    else:
        text += "，生活的气息和历史的痕迹交织在一起。"

    if evidence and evidence != "No visible evidence found here.":
        text += f"\n\n你注意到了这些：\n{evidence}"

    return text


# ---- 缓存辅助 ----

def _compute_cache_key(voice: str, query_type: str, context: dict) -> str:
    """计算缓存 key。"""
    sorted_context = json.dumps(context, sort_keys=True, default=str)
    payload = f"{voice}|{query_type}|{sorted_context}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def clear_cache():
    """清空缓存。"""
    global _cache
    _cache.clear()
