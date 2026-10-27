#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 行为评测。

测的不是「文案好不好」，而是「行为对不对」：
    预算不足会不会拒绝、没数据会不会停、异常能不能抓到、
    复写后合规有没有清零、同输入是否稳定。

用法：
    python eval/run_eval.py                # 离线规则规划器（默认，无需 key）
    python eval/run_eval.py --planner llm  # 用真实模型跑同一套断言
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import llm, planner, runner  # noqa: E402

# 保证 trace 里能看到日报与邀约的关键字段（runner 默认会裁掉大字段）
_orig_shrink = runner._shrink


def _shrink(obs, limit=400):
    if isinstance(obs, dict) and "markdown" in obs:
        return {"markdown": obs["markdown"][:200], "p0": obs.get("p0"),
                "p1": obs.get("p1"), "roi": obs.get("roi")}
    if isinstance(obs, dict) and "messages" in obs:
        return {"count": obs.get("count"),
                "messages": [{k: m.get(k) for k in ("kol_id", "handle", "subject", "body", "mode")}
                             for m in obs["messages"]]}
    return _orig_shrink(obs, limit)


runner._shrink = _shrink


def run_one(spec, use_llm):
    p = (planner.LLMPlanner() if use_llm
         else planner.RulePlanner(budget=spec.get("budget"), sales_path=spec.get("sales"),
                                 search_kwargs=spec.get("search_kwargs")))
    agent = runner.Agent(p, trace_dir=os.path.join(HERE, "_traces"))
    return agent.run(spec["goal"])


def _obs(rec, tool):
    return next((s["observation"] for s in rec["trace"] if s["tool"] == tool), None)


def check(spec, rec):
    exp, fail = spec.get("expect", {}), []
    tools = [s["tool"] for s in rec["trace"]]

    for kw in exp.get("final_contains", []):
        if kw not in (rec["final"] or ""):
            fail.append(f"结论缺少「{kw}」")

    if "feasible" in exp:
        al = _obs(rec, "allocate_budget")
        got = bool(al and al.get("feasible") is True)
        if got != exp["feasible"]:
            fail.append(f"可行性期望 {exp['feasible']}，实际 {got}")

    if exp.get("min_picked"):
        al = _obs(rec, "allocate_budget") or {}
        if al.get("picked_count", 0) < exp["min_picked"]:
            fail.append(f"入选 {al.get('picked_count')} 人 < {exp['min_picked']}")

    if exp.get("matched_zero"):
        sr = _obs(rec, "search_candidates") or {}
        if sr.get("matched", -1) != 0:
            fail.append(f"预期空池，实际 matched={sr.get('matched')}")

    if "exact_steps" in exp and rec["steps"] != exp["exact_steps"]:
        fail.append(f"步数应为 {exp['exact_steps']}，实际 {rec['steps']}（未及时停下）")

    if "min_steps" in exp and rec["steps"] < exp["min_steps"]:
        fail.append(f"步数 {rec['steps']} < {exp['min_steps']}（能力未串全）")

    if exp.get("no_early_stop") and rec["stopped_early"]:
        fail.append("中途终止，未跑完全流程")

    for t in exp.get("tool_contains", []):
        if t not in tools:
            fail.append(f"未调用 {t}")

    if exp.get("review_ok"):
        rv = _obs(rec, "review_campaign")
        if not rv or "overall" not in rv:
            fail.append("未产出复盘结果")
        elif not rv.get("best") or not rv.get("worst"):
            fail.append("复盘缺少最好/最差分组")

    if "monitor_rules" in exp:
        mn = _obs(rec, "monitor_scan") or {}
        got = {a["rule"] for a in mn.get("alerts", [])}
        for rule in exp["monitor_rules"]:
            if rule not in got:
                fail.append(f"未命中规则「{rule}」，实际 {sorted(got)}")
        if mn.get("alert_count", 0) < exp.get("min_alerts", 0):
            fail.append(f"告警数 {mn.get('alert_count')} < {exp.get('min_alerts')}")

    if exp.get("rewrites"):
        n = len([s for s in rec["trace"] if s["tool"] == "rewrite_content"])
        if n < exp["rewrites"]:
            fail.append(f"复写只完成 {n} 条 < {exp['rewrites']}")

    if exp.get("rewrite_compliance_clean"):
        for s in rec["trace"]:
            if s["tool"] != "rewrite_content":
                continue
            ac = (s["observation"].get("after_compliance") or {})
            if ac and not ac.get("pass", True):
                fail.append(f"{s['observation'].get('source_id')} 复写后仍有违规")
                break

    if exp.get("report_ok"):
        rp = _obs(rec, "compose_daily_report") or {}
        if not rp.get("markdown"):
            fail.append("未生成日报正文")

    if exp.get("outreach_ok"):
        ot = _obs(rec, "draft_outreach_message") or {}
        if ot.get("count", 0) < exp.get("min_outreach", 1):
            fail.append(f"邀约话术数量 {ot.get('count')} < {exp.get('min_outreach', 1)}")
        else:
            msg = (ot.get("messages") or [{}])[0]
            if not msg.get("body"):
                fail.append("邀约话术正文为空")

    if exp.get("deterministic"):
        rec2 = run_one(spec, use_llm=False)
        if rec2["final"] != rec["final"]:
            fail.append("两次运行结论不一致")

    return (not fail), "；".join(fail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", default="rule", choices=["rule", "llm"])
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    use_llm = args.planner == "llm"
    if use_llm and not llm.available():
        sys.exit("需要 DEEPSEEK_API_KEY 才能跑 llm 模式")

    specs = json.load(open(os.path.join(HERE, "tasks.json"), encoding="utf-8"))
    print(f"Agent 行为评测：{len(specs)} 条 ｜ 规划器：{args.planner}")
    print("=" * 76)

    passed = 0
    for sp in specs:
        rec = run_one(sp, use_llm)
        ok, why = check(sp, rec)
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {sp['id']}  {sp['desc']}")
        print(f"        步数 {rec['steps']} ｜ {rec['elapsed_ms']}ms" +
              (" ｜ 中途终止" if rec["stopped_early"] else ""))
        if not ok:
            print(f"        ✗ {why}")
        if args.verbose:
            for s in rec["trace"]:
                print(f"        · {s['tool']}")
        print()

    print("=" * 76)
    print(f"通过 {passed}/{len(specs)} = {passed / len(specs):.0%}")
    sys.exit(0 if passed == len(specs) else 1)


if __name__ == "__main__":
    main()
