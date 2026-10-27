#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行入口。

    # 离线基线（无需 key）
    python run_agent.py --goal "指压板新品起量，预算 8000"

    # 全流程（筛选 + 合作 + 复盘 + 监测 + 复写）
    python run_agent.py --goal "全流程跑一遍" --budget 8000

    # 接模型（真正的 agent）
    set DEEPSEEK_API_KEY=sk-xxx
    python run_agent.py --goal "帮我把指压板这波投放复盘一下，找出问题" --planner llm
"""

import argparse
import json
import os
import sys

from agent import llm, planner, runner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goal", default="指压板新品起量，预算 8000")
    ap.add_argument("--budget", type=float, default=8000)
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--planner", default="auto", choices=["auto", "rule", "llm"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show-trace", action="store_true", default=True)
    args = ap.parse_args()

    use_llm = args.planner == "llm" or (args.planner == "auto" and llm.available())
    if use_llm and not llm.available():
        print("[warn] 未检测到 DEEPSEEK_API_KEY / OPENAI_API_KEY，退回离线规则规划器\n", file=sys.stderr)
        use_llm = False

    p = planner.LLMPlanner() if use_llm else planner.RulePlanner(budget=args.budget, top_n=args.top_n)
    agent = runner.Agent(p)
    rec = agent.run(args.goal)

    if args.json:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return

    print("=" * 78)
    print(f"目标：{rec['goal']}")
    print(f"规划器：{rec['planner']} ｜ 步数：{rec['steps']} ｜ 耗时：{rec['elapsed_ms']}ms"
          + (" ｜ 中途终止" if rec["stopped_early"] else ""))
    print("=" * 78)

    if args.show_trace:
        for s in rec["trace"]:
            print(f"\n[{s['step']}] {s['tool']}  ({s['elapsed_ms']}ms)"
                  + (f"  ⚠ {s['flag']}" if s.get("flag") else ""))
            if s.get("thought"):
                print(f"    思考：{s['thought']}")
            if s["args"]:
                print(f"    参数：{json.dumps(s['args'], ensure_ascii=False)}")
            print(f"    观察：{json.dumps(s['observation'], ensure_ascii=False)[:320]}")

    print("\n" + "=" * 78)
    print("结论")
    print("=" * 78)
    print(rec["final"])

    if rec["warnings"]:
        print("\n" + "-" * 78)
        print("风险与待确认")
        for w in dict.fromkeys(rec["warnings"]):
            print(f"  · {w}")

    u = llm.usage_summary()
    if u["calls"]:
        print(f"\n模型调用 {u['calls']} 次 ｜ tokens 输入 {u['prompt_tokens']} / 输出 {u['completion_tokens']} "
              f"｜ 平均延迟 {u['avg_latency_ms']}ms")

    print("\ntrace 已写入 traces/，可逐步骤回放。")


if __name__ == "__main__":
    main()
