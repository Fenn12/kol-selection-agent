#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 客户端：任何 OpenAI 兼容接口都能用（DeepSeek / OpenAI / 本地 vLLM）。

设计约束：
  - 只用标准库 urllib，不引入 openai 包，保证 clone 下来零安装。
  - 所有调用记录 token 与耗时到 logs/llm_usage.jsonl，便于算成本。
  - 失败重试只对 429 / 5xx / 超时生效；参数错误不重试（重试也没用）。
"""

import json
import os
import random
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
DEFAULT_MODEL = os.getenv("MODEL") or "deepseek-chat"

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")


class LLMError(RuntimeError):
    pass


def api_key():
    return os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")


def available():
    return bool(api_key())


def _base():
    return (os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE).rstrip("/")


def _model():
    return os.getenv("MODEL") or DEFAULT_MODEL


def _log(rec):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, "llm_usage.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def chat(messages, tools=None, json_mode=False, temperature=0.3,
         max_tokens=2000, timeout=120, retries=3, tool_choice="auto"):
    """返回 message dict（含 content / tool_calls）。"""
    key = api_key()
    if not key:
        raise LLMError("未配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY")

    payload = {"model": _model(), "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = tool_choice
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = _base() + "/chat/completions"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}

    last_err = None
    for attempt in range(retries):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            usage = data.get("usage", {})
            _log({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": _model(),
                  "latency_ms": int((time.time() - t0) * 1000),
                  "prompt_tokens": usage.get("prompt_tokens"),
                  "completion_tokens": usage.get("completion_tokens"),
                  "tools": bool(tools), "json": json_mode})
            return data["choices"][0]["message"]

        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            # 4xx（除 429）是请求本身的问题，重试无意义
            if e.code != 429 and 400 <= e.code < 500:
                raise LLMError(f"HTTP {e.code}: {detail}") from e
            last_err = f"HTTP {e.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = f"网络错误: {e}"
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMError(f"响应结构异常: {e}") from e

        if attempt < retries - 1:
            time.sleep(1.5 * (2 ** attempt) + random.random())

    raise LLMError(f"调用失败（已重试 {retries} 次）：{last_err}")


def chat_text(messages, **kw):
    """只要文本内容。"""
    msg = chat(messages, **kw)
    return (msg.get("content") or "").strip()


def chat_json(messages, **kw):
    """要 JSON，并做容错解析（模型常包 ```json 围栏）。"""
    msg = chat(messages, json_mode=True, **kw)
    raw = (msg.get("content") or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw.strip("`")
        raw = raw.lstrip("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 兜底：截取第一个 { 到最后一个 }
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            return json.loads(raw[i:j + 1])
        raise LLMError(f"无法解析为 JSON：{raw[:200]}")


def usage_summary():
    """汇总 token 消耗，供 README 与面试时说明成本。"""
    p = os.path.join(LOG_DIR, "llm_usage.jsonl")
    if not os.path.exists(p):
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "avg_latency_ms": 0}
    calls, pt, ct, lat = 0, 0, 0, []
    for line in open(p, encoding="utf-8"):
        d = json.loads(line)
        calls += 1
        pt += d.get("prompt_tokens") or 0
        ct += d.get("completion_tokens") or 0
        lat.append(d.get("latency_ms") or 0)
    return {"calls": calls, "prompt_tokens": pt, "completion_tokens": ct,
            "avg_latency_ms": int(sum(lat) / len(lat)) if lat else 0}
