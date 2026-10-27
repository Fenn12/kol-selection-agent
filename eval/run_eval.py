#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 层评测：测的不是「文案好不好」，而是「行为对不对」。

一个能说会道但会编造达人的 agent，比一个说话笨拙但会拒绝的 agent 危险得多。
所以这里全部是行为断言：

    会不会在预算不足时拒绝
    会不会在没数据时停下
    会不会跳步直接给名单
    同样输入是否稳定

用法：python eval/run_eval.py [--verbose]
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import loop  # noqa: E402


def run_one(spec):
    planner = loop.ScriptedPlanner(budget=spec.get("budget"),
                                   sales_path=spec.get("sales"),
                                   search_kwargs=spec.get("search_kwargs"))
    agent = loop.Agent(planner, trace_dir=os.path.join(HERE, "_traces"))
    return agent.run(spec["task"])


def check(spec, rec):
    """返回 (通过?, 说明)"""
    exp = spec.get("expect", {})
    fail = []

    if "final_contains" in exp:
        for kw in exp["final_contains"]:
            if kw not in (rec["final"] or ""):
                fail.append(f"结论缺少关键词「{kw}」")

    if "feasible" in exp:
        alloc = next((s["observation"] for s in rec["trace"] if s["tool"] == "allocate_budget"), None)
        got = bool(alloc and alloc.get("feasible") is True)
        if got != exp["feasible"]:
            fail.append(f"可行性与预期不符：期望 {exp['feasible']}，实际 {got}")

    if exp.get("min_picked"):
        alloc = next((s["observation"] for s in rec["trace"] if s["tool"] == "allocate_budget"), None)
        n = (alloc or {}).get("picked_count", 0)
        if n < exp["min_picked"]:
            fail.append(f"入选人数不足：期望≥{exp['min_picked']}，实际 {n}")

    if exp.get("matched_zero"):
        sr = next((s["observation"] for s in rec["trace"] if s["tool"] == "search_candidates"), None)
        if (sr or {}).get("matched", -1) != 0:
            fail.append(f"预期候选池为空，实际 matched={(sr or {}).get('matched')}")

    if "max_steps" in exp and rec["steps"] > exp["max_steps"]:
        fail.append(f"步数超限：{rec['steps']} > {exp['max_steps']}")

    if "exact_steps" in exp and rec["steps"] != exp["exact_steps"]:
        fail.append(f"步数应为 {exp['exact_steps']}，实际 {rec['steps']}（说明没有及时停下）")

    if "tool_sequence" in exp:
        got = [s["tool"] for s in rec["trace"]]
        if got != exp["tool_sequence"]:
            fail.append(f"工具顺序不符：{' → '.join(got)}")

    if exp.get("deterministic"):
        rec2 = run_one(spec)
        if rec2["final"] != rec["final"]:
            fail.append("两次运行结论不一致")

    return (not fail), "；".join(fail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    specs = json.load(open(os.path.join(HERE, "tasks.json"), encoding="utf-8"))
    print(f"Agent 行为评测：{len(specs)} 条任务｜规划器：scripted（离线基线）")
    print("=" * 74)

    passed = 0
    for sp in specs:
        rec = run_one(sp)
        ok, why = check(sp, rec)
        passed += ok
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {sp['id']}  {sp['desc']}")
        print(f"        步数 {rec['steps']} ｜ 耗时 {rec['elapsed_ms']}ms")
        if not ok:
            print(f"        ✗ {why}")
        if args.verbose:
            for s in rec["trace"]:
                print(f"        · {s['tool']}({json.dumps(s['args'], ensure_ascii=False)})")
        print()

    print("=" * 74)
    print(f"通过 {passed}/{len(specs)} = {passed / len(specs):.0%}")
    sys.exit(0 if passed == len(specs) else 1)


if __name__ == "__main__":
    main()
