#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка здоровья: был ли успешный запуск дайджеста за последние сутки."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alert import send_alert  # noqa: E402


def api(path, token):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("[health] нет GITHUB_TOKEN/GITHUB_REPOSITORY")
        return 1

    runs = api(f"/repos/{repo}/actions/workflows/daily.yml/runs?per_page=5", token)
    runs = runs.get("workflow_runs", [])
    problems = []

    if not runs:
        problems.append("нет ни одного запуска дайджеста")
    else:
        last = runs[0]
        created = datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - created
        if last.get("status") != "completed" and age < timedelta(hours=3):
            print(f"[health] OK: запуск {last['id']} ещё выполняется")
            return 0
        if age > timedelta(hours=26):
            problems.append(f"последний запуск был {age.days} дн. назад")
        if last.get("conclusion") != "success":
            problems.append(f"последний запуск: {last.get('conclusion') or last.get('status')}")

    if not problems:
        print(f"[health] OK: запуск {runs[0]['id']} успешен")
        return 0

    message = ("⚠️ Velo Digest: " + "; ".join(problems)
               + f"\nhttps://github.com/{repo}/actions")
    print(message)
    send_alert(message)
    return 1


if __name__ == "__main__":
    sys.exit(main())
