#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор статического сайта из issues/*.json: SEO, RSS, sitemap, адаптив."""
import html
import json
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ISSUES_DIR = ROOT / "issues"
SITE_DIR = ROOT / "site"

CFG = json.loads((ROOT / "config.json").read_text("utf-8"))
SITE_CFG = CFG.get("site", {})
TITLE = SITE_CFG.get("title", "Новости для нас")
BASE = (os.environ.get("SITE_URL") or SITE_CFG.get("url", "")).rstrip("/")
CHANNEL = SITE_CFG.get("channel", "")
CHANNEL_NAME = (CFG.get("channel") or {}).get("name", "")

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"]

CSS = """
:root{--bg:#0e1621;--card:#182533;--text:#e9eef5;--muted:#93a1b1;--link:#64b5ef;
--accent:#ffd166;--line:#25384a;--radius:18px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 700px at 50% -10%,#22324a 0%,var(--bg) 55%) no-repeat,var(--bg);
background-attachment:fixed;color:var(--text);font:16px/1.65 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:760px;margin:0 auto;padding:26px 18px 64px}
.site-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:26px}
.brand{font-weight:700;font-size:1.05rem;letter-spacing:.02em}
.brand span{color:var(--accent)}
.tg{font-size:.95rem;border:1px solid var(--line);padding:7px 12px;border-radius:999px}
h1{font-size:clamp(1.55rem,5.2vw,2.25rem);line-height:1.15;margin:.2em 0 .35em}
.meta{color:var(--muted);font-size:.95rem;margin:0 0 18px}
.intro{background:var(--card);border-left:4px solid var(--accent);border-radius:12px;padding:14px 16px;margin:0 0 26px;color:#dfe7f1}
.item{border-top:1px solid var(--line);padding:20px 0}
.item h2{font-size:clamp(1.1rem,3.4vw,1.3rem);line-height:1.3;margin:0 0 8px}
.item p{margin:0 0 10px;color:#cdd7e3}
.src{font-size:.9rem;color:var(--muted)}
.rates{margin:30px 0 0;padding:16px 18px;background:var(--card);border-radius:var(--radius)}
.rates b{color:var(--accent);font-weight:600}
.rates div{margin:4px 0;font-variant-numeric:tabular-nums}
.cta{display:inline-block;margin:26px 0 0;padding:12px 20px;border-radius:999px;
background:var(--accent);color:#1b1405;font-weight:700}
.cta:hover{text-decoration:none;filter:brightness(1.06)}
.archive{margin-top:44px;border-top:1px solid var(--line);padding-top:20px}
.archive h2{font-size:1.05rem;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.08em}
.archive ul{list-style:none;padding:0;margin:0}
.archive li{padding:10px 0;border-bottom:1px solid var(--line)}
.archive a{display:flex;justify-content:space-between;gap:12px}
.archive span{color:var(--muted);font-size:.9rem;white-space:nowrap}
footer{margin-top:48px;color:var(--muted);font-size:.85rem;line-height:1.5}
@media (max-width:520px){.wrap{padding:20px 14px 48px}.rates{font-size:.95rem}}
@media (prefers-reduced-motion:no-preference){a,.cta{transition:filter .15s ease}}
"""


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


def news_word(n):
    return f"{n} {plural(n, ('новость', 'новости', 'новостей'))}"


def esc(value):
    return html.escape(value or "", quote=True)


def url_for(path=""):
    if not BASE:
        return path or "./"
    return f"{BASE}/{path}" if path else f"{BASE}/"


def issue_url(issue):
    return url_for(f"{issue['date'][:10]}.html")


def pretty_date(iso):
    day = datetime.fromisoformat(iso)
    return f"{day.day} {MONTHS[day.month - 1]}, {WEEKDAYS[day.weekday()]}"


def description(issue):
    text = issue.get("intro", "")
    if not text and issue.get("items"):
        text = issue["items"][0].get("title", "")
    text = " ".join(text.split())
    return text[:160]


def render_rates(issue):
    rates = issue.get("rates") or {}
    fiat = rates.get("fiat") or []
    crypto = rates.get("crypto") or []
    if not fiat and not crypto:
        return ""
    rows = []
    if fiat:
        rows.append("<div>💱 " + " · ".join(f"<b>{esc(x)}</b>" for x in fiat) + "</div>")
    if crypto:
        rows.append("<div>₿ " + " · ".join(f"<b>{esc(x)}</b>" for x in crypto) + "</div>")
    return '<section class="rates" aria-label="Курсы">' + "".join(rows) + "</section>"


def render_items(issue):
    parts = []
    for item in issue.get("items", []):
        block = ['<article class="item">']
        block.append(f"<h2>{esc(item.get('title'))}</h2>")
        if item.get("summary"):
            block.append(f"<p>{esc(item['summary'])}</p>")
        if item.get("url"):
            block.append(
                f'<p class="src">Источник: <a href="{esc(item["url"])}" '
                f'rel="nofollow noopener" target="_blank">{esc(item.get("source") or "ссылка")}</a></p>'
            )
        block.append("</article>")
        parts.append("".join(block))
    return "\n".join(parts)


def ld_json(issue):
    items = []
    for index, item in enumerate(issue.get("items", []), 1):
        items.append({
            "@type": "ListItem",
            "position": index,
            "name": item.get("title", ""),
            "url": item.get("url", ""),
        })
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": f"{TITLE} — {pretty_date(issue['date'])}",
        "description": description(issue),
        "datePublished": issue["date"],
        "dateModified": issue["date"],
        "inLanguage": "ru",
        "mainEntityOfPage": issue_url(issue),
        "author": {"@type": "Organization", "name": TITLE},
        "publisher": {"@type": "Organization", "name": TITLE},
        "about": {"@type": "ItemList", "itemListElement": items},
    }
    return json.dumps(data, ensure_ascii=False)


def page(issue, all_issues, is_index=False):
    title = f"{TITLE} — {pretty_date(issue['date'])}"
    desc = description(issue)
    canonical = url_for() if is_index else issue_url(issue)
    weather = issue.get("weather")
    meta_line = pretty_date(issue["date"])
    if weather:
        meta_line += f" · Гродно, {weather['temp']:+d}°, {weather['desc']}"
    meta_line += f" · {news_word(len(issue.get('items', [])))}"

    archive = []
    for other in all_issues:
        if other["date"][:10] == issue["date"][:10]:
            continue
        archive.append(
            f'<li><a href="{issue_url(other)}"><strong>{esc(pretty_date(other["date"]))}</strong>'
            f'<span>{news_word(len(other.get("items", [])))}</span></a></li>'
        )
    archive_html = ""
    if archive:
        archive_html = (
            '<nav class="archive" aria-label="Архив выпусков"><h2>Архив</h2><ul>'
            + "".join(archive[:30]) + "</ul></nav>"
        )

    channel_html = ""
    if CHANNEL:
        channel_html = (f'<p><a class="cta" href="{esc(CHANNEL)}" rel="noopener">'
                        f'Читать в Telegram {esc(CHANNEL_NAME)}</a></p>')

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta name="theme-color" content="#0e1621">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{esc(TITLE)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:locale" content="ru_RU">
<meta property="article:published_time" content="{esc(issue['date'])}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<link rel="alternate" type="application/rss+xml" title="{esc(TITLE)}" href="{url_for('feed.xml')}">
<link rel="stylesheet" href="assets/style.css">
<script type="application/ld+json">{ld_json(issue)}</script>
</head>
<body>
<div class="wrap">
<header class="site-head">
  <div class="brand">🚴 {esc(TITLE)} <span>· Беларусь и Гродно</span></div>
  <a class="tg" href="{esc(CHANNEL)}" rel="noopener">Telegram</a>
</header>
<main>
<article>
  <h1>{esc(TITLE)}</h1>
  <p class="meta">{esc(meta_line)}</p>
  <p class="intro">{esc(issue.get('intro'))}</p>
  {render_items(issue)}
  {render_rates(issue)}
  {channel_html}
</article>
{archive_html}
</main>
<footer>
  <p>{esc(TITLE)} — ежедневный велодайджест Беларуси и Гродно. Обновляется автоматически.</p>
  <p><a href="{url_for()}">Главная</a> · <a href="{url_for('feed.xml')}">RSS</a></p>
</footer>
</div>
</body>
</html>
"""


def feed(issues):
    entries = []
    for issue in issues[:20]:
        link = issue_url(issue)
        entries.append(
            "<item>"
            f"<title>{escape(f'{TITLE} — {pretty_date(issue['date'])}')}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"true\">{escape(link)}</guid>"
            f"<pubDate>{datetime.fromisoformat(issue['date']).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
            f"<description>{escape(description(issue))}</description>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{escape(TITLE)}</title>"
        f"<link>{escape(url_for())}</link>"
        f"<description>{escape(TITLE)} — велодайджест Беларуси и Гродно</description>"
        "<language>ru</language>"
        + "".join(entries) +
        "</channel></rss>"
    )


def sitemap(issues):
    urls = [f"<url><loc>{escape(url_for())}</loc></url>"]
    for issue in issues:
        urls.append(
            f"<url><loc>{escape(issue_url(issue))}</loc>"
            f"<lastmod>{issue['date'][:10]}</lastmod></url>"
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls) + "</urlset>")


def main():
    issues = []
    if ISSUES_DIR.exists():
        for path in sorted(ISSUES_DIR.glob("*.json"), reverse=True):
            try:
                issues.append(json.loads(path.read_text("utf-8")))
            except Exception as exc:  # noqa: BLE001
                print(f"[site] пропуск {path.name}: {exc}")

    if not issues:
        print("[site] нет выпусков — сайт не собираем")
        return 1

    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "assets").mkdir(exist_ok=True)
    (SITE_DIR / "assets" / "style.css").write_text(CSS.strip() + "\n", "utf-8")

    for index, issue in enumerate(issues):
        html_text = page(issue, issues, is_index=(index == 0))
        (SITE_DIR / f"{issue['date'][:10]}.html").write_text(html_text, "utf-8")
        if index == 0:
            (SITE_DIR / "index.html").write_text(html_text, "utf-8")

    (SITE_DIR / "feed.xml").write_text(feed(issues), "utf-8")
    (SITE_DIR / "sitemap.xml").write_text(sitemap(issues), "utf-8")
    (SITE_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n" + (f"Sitemap: {url_for('sitemap.xml')}\n" if BASE else ""),
        "utf-8",
    )
    print(f"[site] собрано {len(issues)} выпусков → {SITE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
