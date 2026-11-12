import sys, os
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

now = datetime.now(timezone.utc)
items = [
    {"title": "Кубок Беларуси по велотреку: яркие финалы", "url": "https://example.com/1",
     "source": "Sport5.by", "source_short": "Sport5.by", "summary": "",
     "dt": now, "kind": "cycling", "category": ""},
    {"title": "Велопробег в Гродно собрал сотни участников", "url": "https://example.com/2",
     "source": "Гродно 24", "source_short": "Гродно 24", "summary": "",
     "dt": now, "kind": "grodno", "category": ""},
    {"title": "Юная велогонщица из Бреста — призёр международной гонки", "url": "https://example.com/3",
     "source": "БелТА", "source_short": "БелТА", "summary": "",
     "dt": now, "kind": "cycling", "category": ""},
]
entries, used, intro, outro, highlights = main.ai_message(items, now)
print("OK intro:", intro)
print("OK highlights:", highlights)
print("OK items:", len(entries))
print(main.render_rich(now, intro, entries, outro, highlights, None, {"temp": 2, "desc": "облачно"}))
