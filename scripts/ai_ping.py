#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Быстрая проверка доступности ИИ-провайдера."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main as bot  # noqa: E402


def main():
    try:
        answer = bot.call_ai("Ты — техническая проверка.", "Ответь одним словом: ок")
        print("[ai-ping] OK:", (answer or "").strip()[:120])
        return 0
    except Exception as exc:  # noqa: BLE001
        print("[ai-ping] FAIL:", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
