#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送：把日报发到邮箱。

没配 SMTP 时不报错，落盘到 outbox/ —— 保证在任何环境都能验证链路，
而不是「没配置就崩」。

环境变量：
    KOL_SMTP_HOST   如 smtp.exmail.qq.com
    KOL_SMTP_PORT   465（SSL）/ 587（STARTTLS）
    KOL_SMTP_USER   登录账号
    KOL_SMTP_PASS   授权码（不是登录密码）
    KOL_SMTP_MODE   ssl | starttls | plain   默认按端口推断
    KOL_MAIL_FROM   发件人，默认同 USER
    KOL_MAIL_TO     收件人，多个用逗号分隔
"""

import os
import smtplib
import ssl
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTBOX = os.path.join(ROOT, "outbox")


def configured():
    return all(os.getenv(k) for k in ("KOL_SMTP_HOST", "KOL_SMTP_USER", "KOL_SMTP_PASS", "KOL_MAIL_TO"))


def _mode():
    m = (os.getenv("KOL_SMTP_MODE") or "").lower()
    if m in ("ssl", "starttls", "plain"):
        return m
    port = int(os.getenv("KOL_SMTP_PORT") or 465)
    return "ssl" if port == 465 else "starttls"


def send(subject, markdown_body, to=None, dry_run=None):
    """发邮件；未配置或 dry_run 时落盘。返回 dict 描述结果。"""
    to = to or os.getenv("KOL_MAIL_TO") or ""
    recipients = [x.strip() for x in to.split(",") if x.strip()]
    if dry_run is None:
        dry_run = not configured()

    if dry_run:
        os.makedirs(OUTBOX, exist_ok=True)
        import time
        path = os.path.join(OUTBOX, f"report-{time.strftime('%Y%m%d-%H%M%S')}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {subject}\n\n{markdown_body}\n")
        return {"sent": False, "mode": "dry_run", "path": path,
                "reason": "未配置 SMTP 或指定了 dry_run，已落盘",
                "recipients": recipients}

    if not recipients:
        return {"sent": False, "mode": "skip", "reason": "KOL_MAIL_TO 为空"}

    msg = MIMEText(markdown_body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    from_addr = os.getenv("KOL_MAIL_FROM") or os.getenv("KOL_SMTP_USER")
    msg["From"] = formataddr((str(Header("投放监测", "utf-8")), from_addr))
    msg["To"] = ", ".join(recipients)

    host = os.getenv("KOL_SMTP_HOST")
    port = int(os.getenv("KOL_SMTP_PORT") or 465)
    user = os.getenv("KOL_SMTP_USER")
    pwd = os.getenv("KOL_SMTP_PASS")
    mode = _mode()

    try:
        if mode == "ssl":
            ctx = ssl.create_default_context()
            srv = smtplib.SMTP_SSL(host, port, context=ctx, timeout=20)
        else:
            srv = smtplib.SMTP(host, port, timeout=20)
            if mode == "starttls":
                srv.starttls(context=ssl.create_default_context())
        with srv:
            srv.login(user, pwd)
            srv.sendmail(from_addr, recipients, msg.as_string())
        return {"sent": True, "mode": mode, "recipients": recipients}
    except Exception as e:
        return {"sent": False, "mode": mode, "error": f"{type(e).__name__}: {e}",
                "recipients": recipients}
