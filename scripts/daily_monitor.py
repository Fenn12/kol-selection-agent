#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日监测任务：扫一遍异常 → 生成日报 → 推送。

设计原则：**默认只在有 P0 时推送**。每天发一封「一切正常」的邮件，
三周后没人会打开它——要发就发需要动手的。

用法：
    python scripts/daily_monitor.py                 # 有 P0 才发
    python scripts/daily_monitor.py --always        # 每天都发
    python scripts/daily_monitor.py --dry-run       # 不发送，只落盘到 outbox/
    python scripts/daily_monitor.py --budget 8000

定时（Windows 计划任务，每天 9:00）：
    schtasks /create /tn "KOLDailyMonitor" /tr "python D://...//scripts//daily_monitor.py" /sc daily /st 09:00

定时（Linux / macOS cron）：
    0 9 * * * cd /path/to/kol-selection-agent && python scripts/daily_monitor.py >> logs/cron.log 2>&1
"""

import argparse
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import env as _env
from agent import datasource, notify, tools_extra  # noqa: E402


_env.load()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=8000)
    ap.add_argument("--always", action="store_true", help="没有 P0 也发")
    ap.add_argument("--dry-run", action="store_true", help="不发送，只落盘")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    src = datasource.describe()
    report = tools_extra.compose_daily_report(budget=args.budget)
    p0, p1 = report["p0"], report["p1"]

    should_send = args.always or p0 > 0
    stamp = datetime.now().strftime("%Y-%m-%d")
    subject = f"[投放监测] {stamp} P0 {p0} / P1 {p1}"

    result = {"date": stamp, "p0": p0, "p1": p1, "roi": report["roi"],
              "datasource": src, "should_send": should_send}

    if not should_send:
        result["notified"] = {"sent": False, "mode": "skipped",
                              "reason": "无 P0 告警，按策略不推送（加 --always 可强制发送）"}
    else:
        # 只有显式 --dry-run 才强制落盘；其余情况交给 notify 判断是否已配置 SMTP
        result["notified"] = notify.send(subject, report["markdown"],
                                         dry_run=True if args.dry_run else None)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{stamp}] 数据源={src.get('source')}  P0={p0} P1={p1} ROI={report['roi']}")
        n = result["notified"]
        if n.get("sent"):
            print(f"  已发送给 {', '.join(n['recipients'])}")
        elif n.get("mode") == "dry_run":
            print(f"  未发送（{n.get('reason')}）→ {n.get('path')}")
        else:
            print(f"  未发送：{n.get('reason') or n.get('error')}")

    # 有 P0 且发送失败 → 非零退出码，让调度器能报警
    return 1 if (p0 > 0 and not result["notified"].get("sent") and result["notified"].get("mode") == "skip") else 0


if __name__ == "__main__":
    sys.exit(main())
