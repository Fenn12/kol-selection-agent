# -*- coding: utf-8 -*-
"""轻量 RAG：本地 Markdown 知识库 + BM25 检索（零依赖）。

设计取舍：
- 不引入向量库和 embedding API：工作台要能离线跑，检索结果要可复现。
- 中文用「单字 + 相邻双字」切分，双字权重加倍；英文/数字按词切。
- 按标题分块，每块 200–400 字，保留标题作为上下文。
"""

import math
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(ROOT, "data", "knowledge")

_CACHE = {"mtime": None, "chunks": [], "df": Counter(), "avgdl": 0.0}


def _tokenize(text):
    text = (text or "").lower()
    ascii_words = re.findall(r"[a-z0-9_]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = ["".join(pair) for pair in zip(cjk, cjk[1:])]
    # 双字重复一次，提高专有词权重
    return ascii_words + cjk + bigrams + bigrams


def _split_chunks(doc_id, text):
    """按二级标题分段，再把段落合并到 200–400 字。"""
    lines = text.splitlines()
    title = ""
    heading = ""
    buf = []
    chunks = []

    def flush():
        nonlocal buf
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            chunks.append({
                "id": f"{doc_id}#{len(chunks)}",
                "doc": doc_id,
                "title": heading or title or doc_id,
                "text": ((heading + "\n") if heading else "") + body,
            })
        buf = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            continue
        if not line.strip():
            continue
        buf.append(line)
        if sum(len(x) for x in buf) >= 320:
            flush()
    flush()
    return chunks


def _load():
    mtime = 0.0
    for name in os.listdir(KNOWLEDGE_DIR):
        if name.endswith(".md"):
            mtime = max(mtime, os.path.getmtime(os.path.join(KNOWLEDGE_DIR, name)))
    if _CACHE["mtime"] == mtime and _CACHE["chunks"]:
        return _CACHE

    chunks = []
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        if not name.endswith(".md"):
            continue
        doc_id = name[:-3]
        text = open(os.path.join(KNOWLEDGE_DIR, name), encoding="utf-8").read()
        chunks.extend(_split_chunks(doc_id, text))

    for c in chunks:
        c["tokens"] = _tokenize(c["text"])

    df = Counter()
    for c in chunks:
        df.update(set(c["tokens"]))
    avgdl = sum(len(c["tokens"]) for c in chunks) / max(len(chunks), 1)

    _CACHE.update({"mtime": mtime, "chunks": chunks, "df": df, "avgdl": avgdl})
    return _CACHE


def list_docs():
    docs = {}
    for c in _load()["chunks"]:
        docs.setdefault(c["doc"], {"doc": c["doc"], "chunks": 0, "title": c["title"]})
        docs[c["doc"]]["chunks"] += 1
    return list(docs.values())


def search(query, top_k=3):
    """BM25 检索，返回 [{doc,title,score,text}]。"""
    query = (query or "").strip()
    if not query:
        return []
    kb = _load()
    chunks, df, avgdl = kb["chunks"], kb["df"], kb["avgdl"]
    n = len(chunks)
    if not n:
        return []

    q_tokens = Counter(_tokenize(query))
    scored = []
    k1, b = 1.5, 0.75
    for c in chunks:
        tf = Counter(c["tokens"])
        dl = len(c["tokens"])
        score = 0.0
        for token in q_tokens:
            if token not in tf:
                continue
            idf = math.log(1 + (n - df[token] + 0.5) / (df[token] + 0.5))
            freq = tf[token]
            score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: -x[0])
    hits = []
    for score, c in scored[:top_k]:
        hits.append({
            "doc": c["doc"],
            "title": c["title"],
            "chunk": c["id"],
            "score": round(score, 4),
            "text": c["text"][:420],
        })
    return hits


def search_context(query, top_k=3, limit=240):
    """给提示词用的紧凑上下文。"""
    hits = search(query, top_k=top_k)
    parts = []
    for h in hits:
        parts.append(f"[{h['doc']} / {h['title']}] {h['text'][:limit]}")
    return hits, "\n".join(parts)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "小红书 合规 极限词"
    for h in search(q, 3):
        print(f"{h['score']:>7.3f}  {h['doc']:<20} {h['title']}")
        print("   ", h["text"][:100].replace("\n", " "))
