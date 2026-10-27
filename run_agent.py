#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行入口。

用法：
    # 离线基线（无需 API key，可直接跑通）
    python run_agent.py --task "指压板新品起量" --budget 8000

    # 接模型（真正的 agent）
    export OPENAI_API_KEY=sk-xxx
    python run_agent.py --task "指压板新品起量" --budget 8000 --planner llm

    # 用自己的真实导出文件（支持 .xls，需 pip install xlrd==1.2.0）
    python run_agent.py --sales "D:/path/to/销售分布.xls" --budget 8000
"""

import argparse
import json
import sys

from agent import loop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="指压板新品起量", help="投放目标描述")
    ap.add_argument("--budget", type=float, default=8000, help="总预算（元）")
    ap.add_argument("--planner", default="auto", choices=["auto", "scripted", "llm"])
    ap.add_argument("--sales", default=None, help="销售分布文件路径，省略则用样例数据")
    ap.add_argument("--json", action="store_true", help="只输出 JSON 结果")
    args = ap.parse_args()

    use_llm = args.planner == "llm" or (args.planner == "auto" and loop.LLMPlanner.available())
    if use_llm and not loop.LLMPlanner.available():
        print("[warn] 未配置 OPENAI_API_KEY，退回离线基线规划器\n", file=sys.stderr)
        use_llm = False

    planner = loop.LLMPlanner() if use_llm else loop.ScriptedPlanner(
        budget=args.budget, sales_path=args.sales)

    agent = loop.Agent(planner)
    rec = agent.run(args.task)

    if args.json:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
        return

    print("=" * 68)
    print(f"任务：{rec['task']}")
    print(f"规划器：{rec['planner']} ｜ 步数：{rec['steps']} ｜ 耗时：{rec['elapsed_ms']}ms")
    print("=" * 68)
    for s in rec["trace"]:
        print(f"\n[{s['step']}] {s['tool']}  ({s['elapsed_ms']}ms)")
        if s.get("thought"):
            print(f"    思考：{s['thought']}")
        print(f"    参数：{json.dumps(s['args'], ensure_ascii=False)}")
        print(f"    观察：{json.dumps(s['observation'], ensure_ascii=False)[:400]}")
    print("\n" + "=" * 68)
    print("结论：")
    print(rec["final"])
    print("=" * 68)
    print("完整 trace 已写入 traces/ 目录，可用于面试回放。")


if __name__ == "__main__":
    main()
