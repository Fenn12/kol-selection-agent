# -*- coding: utf-8 -*-
"""RAG 检索评测：固定 query → 期望文档，计算 Recall@3 / MRR。"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import rag  # noqa: E402

CASES = [
    ("极限词有哪些", ["compliance_rules"]),
    ("第一次算不算绝对化用语", ["compliance_rules"]),
    ("小红书正文写多少字", ["content_playbook"]),
    ("抖音口播前 3 秒要出现什么", ["content_playbook"]),
    ("四维评分的权重", ["kol_selection"]),
    ("S/A/B/C 分层标准", ["kol_selection"]),
    ("预算只用掉 7% 怎么办", ["case_notes", "kol_selection"]),
    ("K040 转化率骤降怎么查", ["case_notes"]),
    ("品牌语气开头能写姐妹们吗", ["brand_voice"]),
    ("客单价置信度低怎么处理", ["case_notes", "kol_selection"]),
]


def main():
    rows = []
    hits_at_3 = 0
    rr_sum = 0.0
    for query, expected in CASES:
        hits = rag.search(query, top_k=3)
        docs = [h["doc"] for h in hits]
        rank = next((i + 1 for i, d in enumerate(docs) if d in expected), 0)
        if rank:
            hits_at_3 += 1
            rr_sum += 1.0 / rank
        rows.append({"query": query, "expected": expected, "returned": docs, "rank": rank})

    n = len(CASES)
    result = {
        "cases": n,
        "recall_at_3": round(hits_at_3 / n, 3),
        "mrr": round(rr_sum / n, 3),
        "hits": hits_at_3,
        "rows": rows,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if hits_at_3 == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
