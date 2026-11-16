#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собирает неофициальные праздники по датам с calend.ru и фильтрует лишнее."""
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "holidays.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122 Safari/537.36"

BLOCK = [
    # религия
    "рождеств", "пасх", "крещен", "троиц", "рамадан", "ураз", "курбан", "ханак",
    "ханук", "песах", "пурим", "шаббат", "шабат", "суккот", "пост", "велик",
    "успен", "благовещ", "вербн", "православ", "католич", "мусульман", "иудей",
    "буддий", "индуист", "свящ", "свят", "богородиц", "никола", "георги",
    "пророк", "апостол", "мученик", "церков", "патриарх", "религи", "языческ",
    "икон", "храм", "монастыр", "крестн", "молитв",
    # политика и государство
    "президент", "парламент", "депутат", "правительств", "революц", "независим",
    "конституц", "флаг", "герб", "гимн", "арми", "военн", "побед", "освобожден",
    "единств", "республик", "суверенитет", "милици", "полици", "выбор",
    # негатив и трагедии
    "террор", "борьб", "памят", "траур", "холокост", "жертв", "войн", "смерт",
    "погиб", "трагед", "катастроф", "авари", "пожар", "наркоман", "спид",
    "туберкулез", "рак ", "инвалид", "беженец", "мигрант",
    # прочее
    "день рождения", "именин", "годовщин", "юбилей",
]


def blocked(name):
    low = name.lower()
    return any(word in low for word in BLOCK)


def fetch(md):
    url = f"https://www.calend.ru/holidays/{md}/"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", "ignore")


def main():
    result = {}
    days = []
    for month in range(1, 13):
        for day in range(1, 32):
            try:
                time.strptime(f"2025-{month:02d}-{day:02d}", "%Y-%m-%d")
            except ValueError:
                continue
            days.append(f"{month:02d}-{day:02d}")

    for index, md in enumerate(days, 1):
        names = []
        for attempt in range(2):
            try:
                html_text = fetch(md)
                names = re.findall(r'<span class="title"><a[^>]*>([^<]+)</a>', html_text)
                break
            except Exception:  # noqa: BLE001
                time.sleep(2)
        clean = []
        for name in names:
            name = " ".join(name.split())
            if len(name) < 5 or blocked(name):
                continue
            if name not in clean:
                clean.append(name)
        result[md] = clean
        if index % 30 == 0:
            print(f"[holidays] {index}/{len(days)}", flush=True)
        time.sleep(0.35)

    result["_rules"] = [
        {"type": "day_of_year", "n": 256, "name": "День программиста"},
        {"type": "last_weekday", "month": 7, "weekday": 4,
         "name": "День системного администратора"},
    ]
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    covered = sum(1 for v in result.values() if v)
    print(f"[holidays] дат с праздниками: {covered}/{len(days)} → {OUT.name}")


if __name__ == "__main__":
    main()
