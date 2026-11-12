#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Отправка алерта администратору в Telegram (ADMIN_CHAT_ID)."""
import json
import os
import sys
import urllib.parse
import urllib.request


def send_alert(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("ADMIN_CHAT_ID")
    if not token or not chat:
        print("[alert] ADMIN_CHAT_ID/TELEGRAM_BOT_TOKEN не заданы — алерт только в лог")
        return False
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return bool(json.loads(resp.read()).get("ok"))


def main():
    text = " ".join(sys.argv[1:]) or "⚠️ Velo Digest: проблема"
    ok = send_alert(text)
    print("[alert] отправлен" if ok else "[alert] не отправлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())
