#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ежедневный велодайджест Беларуси (с позитивными новостями Гродно).

Как работает:
  1. Собирает новости из RSS (Google News по запросам + прямые ленты).
  2. Грубо отсекает политику/происшествия/негатив по ключевым словам.
  3. Отдаёт список ИИ-модели: она отбирает лучшее, переписывает в позитивном
     тоне и возвращает готовый текст (ссылки берутся из наших данных, не от ИИ).
  4. Публикует пост в Telegram-группу через Bot API.
  5. Если ИИ недоступен — отправляет аккуратный дайджест, собранный без ИИ.

Запуск:
    python main.py --dry-run      # показать пост, ничего не отправлять
    python main.py --no-ai        # проверить режим без ИИ
    python main.py                # отправить в Telegram

Переменные окружения:
    TELEGRAM_BOT_TOKEN  — токен бота (обязательно для отправки)
    TELEGRAM_CHAT_ID    — id группы/канала (обязательно для отправки)
    TELEGRAM_THREAD_ID  — id темы в супергруппе (необязательно)
    AI_API_KEY          — ключ ИИ-провайдера (необязательно, но желательно)
    AI_BASE_URL         — переопределить base_url из config.json
    AI_MODEL            — переопределить модель из config.json
"""
import argparse
import hashlib
import tempfile
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = json.loads((BASE / "config.json").read_text("utf-8"))

sys.path.insert(0, str(BASE))
import extras  # noqa: E402

TZ = timezone(timedelta(hours=3))  # Europe/Minsk — UTC+3 круглый год
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"]
NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

INTROS = [
    "Только хорошие новости: велоспорт Беларуси и жизнь Гродно. Без политики и происшествий.",
    "Свежая порция велоновостей — заряжаемся позитивом на весь день.",
    "Что нового в мире велосипеда? Собрали главное для вас.",
    "Велоновости Беларуси и Гродно: коротко о хорошем.",
    "Подборка дня: велоспорт, город и немного солнечного настроения.",
    "Начинаем день с хороших новостей о велосипедах и родном городе.",
    "Велодайджест выходного дня: самое интересное и доброе.",
]

FALLBACK_TEXT = (
    "Сегодня новостей совсем немного — значит, отличный повод просто "
    "покататься! 🚲\n\nЕсли у вас есть интересная велоистория из Гродно "
    "или Беларуси — присылайте в комментарии."
)


# --------------------------------------------------------------------- utils
def log(msg):
    print(msg, flush=True)


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def strip_tags(text):
    return clean(re.sub(r"<[^>]+>", " ", text or ""))


def short(text, limit):
    text = clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—–-") + "…"


def http_get(url, timeout=25, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    log(f"[warn] не удалось загрузить {url}: {last}")
    return None


def parse_dt(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except Exception:  # noqa: BLE001
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def domain_of(url):
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        host = ""
    return host.replace("www.", "")


def title_tokens(text):
    return set(re.findall(r"[а-яёa-z0-9]{3,}", (text or "").lower()))


def similar(a, b):
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) > 0.62


# --------------------------------------------------------------------- state
def item_key(item):
    tokens = sorted(title_tokens(item.get("title", "")))
    base = " ".join(tokens) or (item.get("title") or item.get("url") or "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def load_state(path):
    try:
        data = json.loads(Path(path).read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sent"), dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {"sent": {}}


def save_state(path, state):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    state["sent"] = {k: v for k, v in state.get("sent", {}).items() if v >= cutoff}
    Path(path).write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")


def mark_sent(state, items, now):
    stamp = now.isoformat()
    for item in items:
        state.setdefault("sent", {})[item_key(item)] = stamp


# --------------------------------------------------------------------- collect
def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(node, name):
    for child in node:
        if local_name(child.tag) == name:
            return child.text or ""
    return ""


def parse_rss(raw, kind):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log(f"[warn] битый RSS: {exc}")
        return []

    items = []
    for node in root.iter():
        if local_name(node.tag) != "item":
            continue
        title = clean(child_text(node, "title"))
        link = clean(child_text(node, "link"))
        if not title or not link:
            continue
        source = clean(child_text(node, "source"))
        category = clean(child_text(node, "category"))
        summary = strip_tags(child_text(node, "description"))
        dt = parse_dt(clean(child_text(node, "pubDate")))

        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].strip()
        if not source:
            source = domain_of(link)
        if summary and (summary.lower().startswith(title.lower()[:40])
                        or len(summary) < 30):
            summary = ""

        items.append({
            "title": title,
            "url": link,
            "source": source,
            "source_short": short(source, 30),
            "summary": short(summary, 220),
            "dt": dt or datetime.now(timezone.utc),
            "kind": kind,
            "category": category,
        })
    return items


def google_items(query, kind):
    params = {"q": query, "hl": "ru", "gl": "BY", "ceid": "BY:ru"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    raw = http_get(url)
    if not raw:
        return []
    return parse_rss(raw, kind)


def collect(now, state):
    digest_cfg = CFG["digest"]
    items = []

    for query in CFG["queries"]["cycling"]:
        items.extend(google_items(query, "cycling"))
    for query in CFG["queries"]["grodno"]:
        items.extend(google_items(query, "grodno"))
    for feed in CFG.get("direct_feeds", []):
        raw = http_get(feed["url"])
        if not raw:
            continue
        for item in parse_rss(raw, feed.get("kind", "grodno")):
            if item["category"]:
                allowed_cats = [c.lower() for c in feed.get("allowed_categories", [])]
                if item["category"].lower() not in allowed_cats:
                    continue
            items.append(item)

    log(f"[collect] получено {len(items)} новостей из RSS")

    kept = [item for item in items if allowed(item, now)]
    log(f"[filter] после фильтра негатива/свежести — {len(kept)}")

    unique = []
    for item in sorted(kept, key=rank, reverse=True):
        if any(similar(item["title"], other["title"]) for other in unique):
            continue
        unique.append(item)

    unseen = [item for item in unique if item_key(item) not in state.get("sent", {})]
    skipped = len(unique) - len(unseen)
    limit = digest_cfg.get("max_input_items", 30)
    return unseen[:limit], skipped


def allowed(item, now):
    text = f"{item['title']} {item['summary']} {item['category']}".lower()

    if any(word in text for word in CFG["negative_keywords"]):
        return False

    if item["kind"] == "grodno":
        topics = any(word in text for word in CFG["grodno_topics"])
        if not topics:
            return False
        max_age = timedelta(hours=CFG["digest"]["lookback_hours_grodno"])
    else:
        if not any(word in text for word in CFG["cycling_keywords"]):
            return False
        max_age = timedelta(hours=CFG["digest"]["lookback_hours_cycling"])

    age = now - item["dt"]
    if age > max_age or age < timedelta(hours=-24):
        return False
    return True


def rank(item):
    text = (item["title"] + " " + item["summary"]).lower()
    score = sum(1 for word in CFG["cycling_keywords"] if word in text)
    if item["kind"] == "cycling":
        score += 2
    return (score, item["dt"])


# --------------------------------------------------------------------- compose
def plural(n, forms):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def item_emoji(text):
    text = (text or "").lower()
    if any(w in text for w in ("гонк", "кубок", "чемпионат", "турнир", "побед",
                               "рекорд", "медал", "спорт", "трек", "этап")):
        return "🏁"
    if any(w in text for w in ("фестиваль", "праздник", "концерт", "выставк",
                               "ярмарк", "юбилей", "музей", "театр")):
        return "🎉"
    if any(w in text for w in ("велодорож", "прокат", "инфраструктур", "парк",
                               "город", "ремонт", "открыт", "благоустройств")):
        return "🏙️"
    return "🚴"


def weather_text(weather):
    if not weather:
        return ""
    return f"Гродно, {weather['temp']:+d}°, {weather['desc']}"


def render(now, intro, entries, outro, highlights=None, rates=None, weather=None):
    day = now.astimezone(TZ)
    highlights = highlights or []
    wl = weather_text(weather)
    head = [
        "🚴 <b>Велодайджест Беларуси</b>",
        f"🗓 {day.day} {MONTHS[day.month - 1]}, {WEEKDAYS[day.weekday()]}"
        + (f" · {wl}" if wl else ""),
        "",
        html.escape(intro),
        "",
    ]
    if highlights:
        head.append("<b>Главное за день</b>")
        head += [f"• {html.escape(h)}" for h in highlights]
        head.append("")

    body = []
    for index, entry in enumerate(entries):
        body.append(f"{NUMBERS[index]} <b>{html.escape(entry['title'])}</b>")
        if entry.get("summary"):
            body.append(html.escape(entry["summary"]))
        if entry.get("url"):
            label = html.escape(entry.get("source") or "Источник")
            body.append(f"🔗 <a href=\"{html.escape(entry['url'], quote=True)}\">{label}</a>")
        body.append("")

    fiat, crypto = extras.rates_lines(rates)
    tail = []
    if fiat:
        tail.append("💱 " + " · ".join(fiat))
    if crypto:
        tail.append("₿ " + " · ".join(crypto))
    if tail:
        tail.append("")
    tail += [html.escape(outro), "", "#велоБеларусь #Гродно"]

    text = "\n".join(head + body + tail)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > 3900:
        text = text[:3900].rsplit("\n", 1)[0] + "…"
    return text


def render_rich(now, intro, entries, outro, highlights=None, rates=None, weather=None):
    """Красивый пост в формате rich message (Bot API 10.x)."""
    day = now.astimezone(TZ)
    highlights = highlights or []
    wl = weather_text(weather)
    subtitle = f"{day.day} {MONTHS[day.month - 1]}, {WEEKDAYS[day.weekday()]}"
    if wl:
        subtitle += f" · {wl}"
    subtitle += f" · {len(entries)} {plural(len(entries), ('новость', 'новости', 'новостей'))}"

    parts = [
        "<h2>🚴 Велодайджест Беларуси</h2>",
        f"<p>{html.escape(subtitle)}</p>",
        f"<blockquote>{html.escape(intro)}</blockquote>",
    ]
    if highlights:
        parts.append("<h3>Главное за день</h3>")
        parts.append("<ul>" + "".join(f"<li>{html.escape(h)}</li>" for h in highlights) + "</ul>")

    parts.append("<hr/>")
    for index, entry in enumerate(entries, 1):
        emoji = item_emoji(f"{entry.get('title', '')} {entry.get('summary', '')}")
        parts.append(f"<h4>{emoji} {index}. {html.escape(entry['title'])}</h4>")
        if entry.get("summary"):
            parts.append(f"<p>{html.escape(entry['summary'])}</p>")
        if entry.get("url"):
            label = html.escape(entry.get("source") or "Источник")
            parts.append(
                f"<p><a href=\"{html.escape(entry['url'], quote=True)}\">→ {label}</a></p>"
            )

    fiat, crypto = extras.rates_lines(rates)
    if fiat or crypto:
        parts.append("<hr/>")
        if fiat:
            parts.append("<p>💱 " + " · ".join(f"<b>{html.escape(x)}</b>" for x in fiat) + "</p>")
        if crypto:
            parts.append("<p>₿ " + " · ".join(f"<b>{html.escape(x)}</b>" for x in crypto) + "</p>")

    parts.append("<hr/>")
    outro_clean = re.sub(r"^[\s🌿🍀☀️]+", "", outro).strip() or "Хорошего дня и попутного ветра!"
    parts.append(f"<p>🌿 {html.escape(outro_clean)}</p>")
    parts.append("<p>#велоБеларусь #Гродно</p>")
    return "\n".join(parts)


def simple_message(items, now):
    cfg = CFG["digest"]
    max_items = cfg["max_items"]
    min_cycling = cfg["min_cycling"]

    cycling = [i for i in items if i["kind"] == "cycling"]
    grodno = [i for i in items if i["kind"] == "grodno"]

    selected = cycling[:max_items]
    if len(selected) < min_cycling:
        for item in grodno:
            if len(selected) >= max_items:
                break
            if any(similar(item["title"], s["title"]) for s in selected):
                continue
            selected.append(item)

    intro = INTROS[now.weekday() % len(INTROS)]
    outro = "🌿 Хорошего дня и попутного ветра!"
    if not selected:
        entries = [{"title": "Тихий день", "summary": FALLBACK_TEXT,
                    "url": "", "source": ""}]
        return entries, [], intro, outro

    return selected, selected, intro, outro


# --------------------------------------------------------------------- AI
def ai_settings():
    cfg = dict(CFG.get("ai", {}))
    cfg["base_url"] = (os.environ.get("AI_BASE_URL") or cfg.get("base_url", "")).rstrip("/")
    cfg["model"] = os.environ.get("AI_MODEL") or cfg.get("model", "")
    cfg["api_key"] = os.environ.get("AI_API_KEY", "")
    return cfg


def build_prompt(items, now):
    cfg = CFG["digest"]
    lines = []
    for index, item in enumerate(items, 1):
        kind = "Гродно" if item["kind"] == "grodno" else "вело"
        date = item["dt"].astimezone(TZ).strftime("%d.%m")
        lines.append(f"{index}. [{kind}] {item['title']} — {item['source_short']} ({date})")
    listing = "\n".join(lines)

    system = (
        "Ты — редактор ежедневного велодайджеста о Беларуси и Гродно. "
        "Пишешь по-русски, дружелюбно и позитивно. "
        "Категорически не включаешь политику, происшествия, криминал, ДТП, "
        "трагедии, скандалы, военную тематику и любой негатив. "
        "Не выдумываешь факты, которых нет в списке."
    )

    user = f"""Ниже — новости, собранные за последние дни.

{listing}

Собери пост для Telegram-группы о велосипедах и велодвижении в Беларуси.

Правила:
1. Отбери до {cfg['max_items']} самых интересных и релевантных новостей. Приоритет — велоспорт, велогонки, велопробеги, велоинфраструктура, велосипеды в Беларуси.
2. Исключи политику, происшествия, аварии, криминал, трагедии, скандалы, жалобы, негатив и всё, что портит настроение.
3. Если велоновостей меньше {cfg['min_cycling']}, добавь 1–3 позитивные новости о Гродно (спорт, культура, город, люди, природа).
4. Каждую новость перепиши своими словами: короткий заголовок (до 70 символов) и 1–2 предложения (до 220 символов). Тон — бодрый, доброжелательный, без канцелярита и без воды.
5. Не добавляй ссылки и не придумывай источники.
6. intro — одно предложение-приветствие (до 140 символов). outro — одна короткая позитивная фраза (до 100 символов).
7. highlights — 2–3 очень короткие фразы «главного за день» (до 90 символов каждая), только факты из новостей.
8. Не включай две новости об одном и том же событии.
9. Верни СТРОГО валидный JSON без markdown и пояснений:
{{"intro": "...", "highlights": ["...", "..."], "items": [{{"id": 1, "title": "...", "summary": "..."}}], "outro": "..."}}
Используй только id из списка выше."""

    return system, user


def _chat_completion(cfg, model, system, user):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens", 1400),
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=cfg.get("timeout", 90)) as resp:
        body = json.loads(resp.read())
    return body["choices"][0]["message"]["content"]


def list_models(cfg):
    req = urllib.request.Request(
        cfg["base_url"] + "/models",
        headers={"Authorization": f"Bearer {cfg['api_key']}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return [m.get("id") for m in data.get("data", []) if m.get("id")]


def call_ai(system, user):
    cfg = ai_settings()
    if not cfg["api_key"]:
        raise RuntimeError("AI_API_KEY не задан")
    if not cfg["base_url"] or not cfg["model"]:
        raise RuntimeError("не заданы base_url/model")

    try:
        content = _chat_completion(cfg, cfg["model"], system, user)
        log(f"[ai] ответила модель {cfg['model']}")
        return content
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        log(f"[ai] модель {cfg['model']} недоступна — ищу альтернативу")
        try:
            models = list_models(cfg)
        except Exception as exc2:  # noqa: BLE001
            raise RuntimeError(f"не удалось получить список моделей: {exc2}") from exc
        log("[ai] доступные модели: " + ", ".join(models[:20]))
        skip = ("image", "tts", "embedding", "live", "audio")
        preferred = [m for m in models
                     if "flash" in m.lower() and not any(x in m.lower() for x in skip)]
        for model in preferred[:3]:
            try:
                log(f"[ai] пробую {model}")
                content = _chat_completion(cfg, model, system, user)
                log(f"[ai] ответила модель {model}")
                return content
            except Exception as exc3:  # noqa: BLE001
                log(f"[ai] {model}: {exc3}")
                continue
        raise


def extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def ai_message(items, now):
    system, user = build_prompt(items, now)
    raw = call_ai(system, user)
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("ИИ вернул не JSON")

    picked, picked_src, seen = [], [], set()
    for entry in data.get("items") or []:
        try:
            idx = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        if idx < 1 or idx > len(items) or idx in seen:
            continue
        seen.add(idx)
        src = items[idx - 1]
        title = short(entry.get("title") or src["title"], 90)
        summary = short(entry.get("summary") or "", 240)
        text = f"{title} {summary}".lower()
        if any(word in text for word in CFG["negative_keywords"]):
            continue
        picked.append({
            "title": title,
            "summary": summary,
            "url": src["url"],
            "source": src["source_short"],
        })
        picked_src.append(src)
        if len(picked) >= CFG["digest"]["max_items"]:
            break

    if not picked:
        raise ValueError("ИИ не отобрал ни одной новости")

    intro = short(data.get("intro") or INTROS[now.weekday() % len(INTROS)], 160)
    outro = short(data.get("outro") or "🌿 Хорошего дня и попутного ветра!", 120)
    if any(word in (intro + " " + outro).lower() for word in CFG["negative_keywords"]):
        intro = INTROS[now.weekday() % len(INTROS)]
        outro = "🌿 Хорошего дня и попутного ветра!"

    highlights = []
    for item in data.get("highlights") or []:
        if not isinstance(item, str):
            continue
        text = short(item, 110)
        if text and not any(word in text.lower() for word in CFG["negative_keywords"]):
            highlights.append(text)
        if len(highlights) >= 3:
            break

    return picked, picked_src, intro, outro, highlights


# --------------------------------------------------------------------- Telegram
def send_telegram(token, chat_id, text):
    cfg = CFG.get("telegram", {})
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true" if cfg.get("disable_web_page_preview", True) else "false",
    }
    thread = os.environ.get("TELEGRAM_THREAD_ID")
    if thread:
        payload["message_thread_id"] = thread

    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    for attempt in range(3):
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                result = json.loads(resp.read())
            if not result.get("ok"):
                raise RuntimeError(f"Telegram: {result}")
            return result
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            if exc.code == 429 and attempt < 2:
                wait = 5
                try:
                    wait = int(json.loads(body)["parameters"]["retry_after"]) + 1
                except Exception:  # noqa: BLE001
                    pass
                log(f"[telegram] 429, ждём {wait} с")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Telegram API {exc.code}: {body}") from exc
    raise RuntimeError("Telegram: не удалось отправить сообщение")


def send_rich(token, chat_id, rich_html):
    """Отправка rich message (Bot API 10.x). При ошибке — исключение, вызывающий делает фолбэк."""
    payload = {"chat_id": chat_id, "rich_message": {"html": rich_html}}
    thread = os.environ.get("TELEGRAM_THREAD_ID")
    if thread:
        try:
            payload["message_thread_id"] = int(thread)
        except ValueError:
            pass

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendRichMessage"
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=40) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rich: {result}")
    return result


def send_photo(token, chat_id, path, caption=None, silent=True):
    """Отправка обложки (multipart/form-data)."""
    import uuid
    boundary = "----velo" + uuid.uuid4().hex
    chunks = []

    def add_field(name, value):
        chunks.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
             f'{value}\r\n').encode("utf-8")
        )

    add_field("chat_id", str(chat_id))
    if silent:
        add_field("disable_notification", "true")
    if caption:
        add_field("caption", caption)

    with open(path, "rb") as handle:
        payload = handle.read()

    chunks.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; '
         f'filename="cover.png"\r\nContent-Type: image/png\r\n\r\n').encode("utf-8")
    )
    chunks.append(payload)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram photo: {result}")
    return result


# --------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description="Велодайджест Беларуси → Telegram")
    parser.add_argument("--dry-run", action="store_true", help="не отправлять, только показать")
    parser.add_argument("--no-ai", action="store_true", help="без ИИ, простой режим")
    parser.add_argument("--state", default=os.environ.get("STATE_FILE", "state.json"),
                        help="файл с уже отправленными новостями")
    parser.add_argument("--classic", action="store_true",
                        help="отправить обычный пост вместо rich message")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    state = load_state(args.state)
    items, skipped = collect(now, state)
    if skipped:
        log(f"[state] пропущено уже отправленных: {skipped}")

    ai_ready = (CFG.get("ai", {}).get("enabled", True)
                and not args.no_ai
                and bool(os.environ.get("AI_API_KEY")))

    weather = extras.fetch_weather() if CFG.get("weather", {}).get("enabled", True) else None
    rates = extras.fetch_rates() if CFG.get("rates", {}).get("enabled", True) else None
    if weather:
        log(f"[weather] Гродно {weather['temp']:+d}°, {weather['desc']}")
    if rates:
        log(f"[rates] валют: {len(rates.get('fiat', []))}, крипто: {len(rates.get('crypto', []))}")

    entries, used, intro, outro, highlights, mode = None, [], "", "", [], "simple"
    if ai_ready and items:
        try:
            log(f"[ai] модель: {ai_settings()['model']}")
            entries, used, intro, outro, highlights = ai_message(items, now)
            mode = "ai"
        except Exception as exc:  # noqa: BLE001
            log(f"[ai] ошибка, переключаюсь на простой режим: {type(exc).__name__}: {exc}")
    elif not args.no_ai:
        log("[ai] AI_API_KEY не задан — работаю в простом режиме")

    if entries is None:
        entries, used, intro, outro = simple_message(items, now)
        highlights = []
        mode = "simple"

    classic = render(now, intro, entries, outro, highlights, rates, weather)
    rich = render_rich(now, intro, entries, outro, highlights, rates, weather)

    log(f"[digest] режим: {mode}, новостей: {len(entries)}, "
        f"rich: {len(rich)} симв., classic: {len(classic)} симв.")

    if args.dry_run:
        print("\n" + "=" * 60 + "\n" + (classic if args.classic else rich) + "\n" + "=" * 60)
        if CFG.get("cover", {}).get("enabled", True):
            try:
                cover = extras.draw_cover(now, weather,
                                          os.path.join(tempfile.gettempdir(), "velo_cover.png"))
                log(f"[cover] {cover}")
            except Exception as exc:  # noqa: BLE001
                log(f"[cover] ошибка: {type(exc).__name__}: {exc}")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log("[error] не заданы TELEGRAM_BOT_TOKEN и/или TELEGRAM_CHAT_ID")
        return 1

    if CFG.get("cover", {}).get("enabled", True):
        try:
            cover = extras.draw_cover(now, weather,
                                      os.path.join(tempfile.gettempdir(), "velo_cover.png"))
            send_photo(token, chat_id, cover, silent=True)
            log("[telegram] обложка отправлена")
        except Exception as exc:  # noqa: BLE001
            log(f"[telegram] обложка не отправлена: {type(exc).__name__}: {exc}")

    use_rich = CFG.get("telegram", {}).get("use_rich", True) and not args.classic
    if use_rich:
        try:
            send_rich(token, chat_id, rich)
            log("[telegram] отправлен rich-пост")
        except Exception as exc:  # noqa: BLE001
            log(f"[telegram] rich не удался ({type(exc).__name__}: {exc}); фолбэк на обычный пост")
            send_telegram(token, chat_id, classic)
            log("[telegram] отправлен обычный пост")
    else:
        send_telegram(token, chat_id, classic)
        log("[telegram] отправлен обычный пост")
    if used:
        mark_sent(state, used, now)
        save_state(args.state, state)
        log(f"[state] записано {len(used)} новостей")
    return 0


if __name__ == "__main__":
    sys.exit(main())
