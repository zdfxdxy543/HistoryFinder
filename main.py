"""
HistoryFinder — CLI 入口
程序化生成世界 → 进入文字冒险 REPL → 探索历史。
"""

import sys
import argparse

from config import RANDOM_SEED, SIM_YEARS, LLM_MODEL_PATH, LLM_N_CTX, LLM_N_THREADS
from simulation.world import World
from game.repl import GameREPL
from narrative.llm_interface import init_llm, is_llm_available


# ---- 统计输出 ----

def dump_statistics(world: World) -> None:
    """输出世界状态和事件/证据分布的基线统计。"""
    alive = [s for s in world.settlements.values() if s.alive]
    ruined = [s for s in world.settlements.values() if not s.alive]

    print(f"========== HistoryFinder 统计报告 ==========")
    print(f"Seed: {world.seed}, 年份: {world.current_year}")
    print(f"聚落: {len(world.settlements)} 个（现存 {len(alive)}，废墟 {len(ruined)}）")
    print(f"历史事件: {len(world.events)} 条")
    print(f"当时记录: {len(world.records)} 份")
    print(f"证据: {len(world.evidence)} 件")

    # 事件按类型分布
    event_types: dict[str, int] = {}
    for e in world.events:
        event_types[e.event_type] = event_types.get(e.event_type, 0) + 1
    print(f"\n--- 事件按类型分布 ---")
    for t, c in sorted(event_types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")

    # 证据按状态分布
    evidence_states: dict[str, int] = {}
    evidence_materials: dict[str, int] = {}
    for evd in world.evidence.values():
        evidence_states[evd.state] = evidence_states.get(evd.state, 0) + 1
        evidence_materials[evd.material] = evidence_materials.get(evd.material, 0) + 1
    print(f"\n--- 证据按状态分布 ---")
    for s, c in sorted(evidence_states.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")
    print(f"\n--- 证据按材质分布 ---")
    for m, c in sorted(evidence_materials.items(), key=lambda x: -x[1]):
        print(f"  {m}: {c}")

    # 人口统计
    if alive:
        pops = [s.population for s in alive]
        print(f"\n--- 人口统计 ---")
        print(f"  最小: {min(pops)}, 最大: {max(pops)}, 平均: {sum(pops)//len(pops)}")

    # 年均事件数
    if world.current_year > 0:
        avg = len(world.events) / world.current_year
        print(f"\n--- 年均事件数: {avg:.1f} ---")

    # 每个聚落的事件数
    print(f"\n--- 每个聚落的事件数 ---")
    for s in sorted(world.settlements.values(), key=lambda s: s.name):
        count = len(world.event_history_by_settlement.get(s.id, []))
        status = "存活" if s.alive else f"废墟({s.destruction_cause})"
        print(f"  {s.name} ({status}): {count} 条事件")

    # 因果链统计（Phase 2）
    caused = [e for e in world.events if e.cause_event_ids]
    print(f"\n--- 因果链统计 ---")
    print(f"  有前置事件的事件: {len(caused)}/{len(world.events)} "
          f"({100*len(caused)/max(len(world.events),1):.0f}%)")

    print(f"=============================================")


# ---- 入口 ----

def main():
    parser = argparse.ArgumentParser(description="HistoryFinder — 历史寻踪")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="世界种子")
    parser.add_argument("--years", type=int, default=SIM_YEARS, help="模拟年数")
    parser.add_argument("--model", type=str, default=LLM_MODEL_PATH, help="LLM 模型路径")
    parser.add_argument("--no-llm", action="store_true", help="禁用 LLM，使用模板模式")
    parser.add_argument("--stats", action="store_true", help="输出统计信息后退出")
    parser.add_argument("--debug-causes", action="store_true", help="打印事件触发因素")
    args = parser.parse_args()

    print("HistoryFinder 启动中……")

    # 初始化世界
    print(f"[模拟] 正在生成世界（seed={args.seed}, years={args.years}）……")
    world = World(seed=args.seed)
    world.debug_causes = args.debug_causes
    world.generate(years=args.years)
    print(f"[模拟] 完成！生成了 {len(world.events)} 个历史事件，{len(world.evidence)} 件证据。")

    # --stats 模式：输出统计并退出
    if args.stats:
        dump_statistics(world)
        return

    # --debug-causes 模式：打印触发因素
    if args.debug_causes:
        print(f"\n========== 事件触发因素 ==========")
        for e in world.events:
            if e.trigger_factors:
                print(f"[{e.year}] {e.title} ({e.event_type})")
                for factor, value in sorted(e.trigger_factors.items(), key=lambda x: -x[1]):
                    print(f"    {factor}: {value:.3f}")
        print(f"===================================\n")

    # 初始化 LLM
    if not args.no_llm:
        print("[LLM] 正在加载模型……")
        init_llm(args.model, n_ctx=LLM_N_CTX, n_threads=LLM_N_THREADS)

    # 进入 REPL
    repl = GameREPL(world)
    repl.run()


if __name__ == "__main__":
    main()
