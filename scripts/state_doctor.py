#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гигиена state.json: чистит старые и битые записи."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import main as bot  # noqa: E402


def main():
    path = ROOT / "state.json"
    state = bot.load_state(path)
    sent = state.get("sent", {})
    before = len(sent)

    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=bot.state_retention_days())).isoformat()
    clean, broken, stale = {}, 0, 0
    for key, value in sent.items():
        if not isinstance(value, str) or not value[:1].isdigit():
            broken += 1
            continue
        if value < cutoff:
            stale += 1
            continue
        clean[key] = value

    state["sent"] = clean
    bot.save_state(path, state)
    print(f"[doctor] было {before}, осталось {len(clean)} "
          f"(старых {stale}, битых {broken}, храним {bot.state_retention_days()} дн.)")


if __name__ == "__main__":
    sys.exit(main())
