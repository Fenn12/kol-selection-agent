#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
.env 加载器（标准库实现，不引 python-dotenv）。

在 server / CLI / 脚本入口第一行调用 load() 即可。
已存在的真实环境变量优先，不会被 .env 覆盖。
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENV_FILE = os.path.join(ROOT, ".env")


def load(path=None):
    p = path or ENV_FILE
    if not os.path.exists(p):
        return {"loaded": 0, "path": p, "exists": False}

    n = 0
    with open(p, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if not k:
                continue
            # 不覆盖已存在的环境变量：部署环境优先
            if k in os.environ and os.environ[k]:
                continue
            os.environ[k] = v
            n += 1
    return {"loaded": n, "path": p, "exists": True}
