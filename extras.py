#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Погода, курсы и обложка для велодайджеста."""
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; VeloDigest/1.0)"

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье"]

WEATHER = {
    0: ("ясно", "sun"), 1: ("малооблачно", "sun"), 2: ("переменная облачность", "partly"),
    3: ("облачно", "cloud"), 45: ("туман", "fog"), 48: ("туман", "fog"),
    51: ("морось", "rain"), 53: ("морось", "rain"), 55: ("морось", "rain"),
    56: ("лёгкий ледяной дождь", "rain"), 57: ("ледяной дождь", "rain"),
    61: ("дождь", "rain"), 63: ("дождь", "rain"), 65: ("сильный дождь", "rain"),
    66: ("ледяной дождь", "rain"), 67: ("ледяной дождь", "rain"),
    71: ("небольшой снег", "snow"), 73: ("снег", "snow"), 75: ("сильный снег", "snow"),
    77: ("снежная крупа", "snow"),
    80: ("ливни", "rain"), 81: ("ливни", "rain"), 82: ("сильные ливни", "rain"),
    85: ("снегопады", "snow"), 86: ("снегопады", "snow"),
    95: ("гроза", "storm"), 96: ("гроза с градом", "storm"), 99: ("гроза с градом", "storm"),
}


def http_json(url, timeout=20, tries=2):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception:  # noqa: BLE001
            time.sleep(1 + attempt)
    return None


# ------------------------------------------------------------------ weather
def fetch_weather():
    """Погода в Гродно на текущий момент (Open-Meteo, без ключа)."""
    url = ("https://api.open-meteo.com/v1/forecast"
           "?latitude=53.6667&longitude=23.8333"
           "&current=temperature_2m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,weather_code"
           "&timezone=Europe%2FMinsk&forecast_days=1")
    data = http_json(url)
    if not data:
        return None
    try:
        cur = data["current"]
        daily = data.get("daily") or {}
        code = int(cur.get("weather_code", 3))
        desc, icon = WEATHER.get(code, ("облачно", "cloud"))
        return {
            "temp": round(float(cur["temperature_2m"])),
            "desc": desc,
            "icon": icon,
            "tmax": round(float(daily["temperature_2m_max"][0])) if daily.get("temperature_2m_max") else None,
            "tmin": round(float(daily["temperature_2m_min"][0])) if daily.get("temperature_2m_min") else None,
        }
    except (KeyError, TypeError, ValueError, IndexError):
        return None


# -------------------------------------------------------------------- rates
def fetch_rates():
    """Курсы НБРБ (BYN) и криптовалют (USD). Любая часть может отсутствовать."""
    result = {"fiat": [], "crypto": [], "date": None}

    data = http_json("https://api.nbrb.by/exrates/rates?periodicity=0")
    if isinstance(data, list):
        wanted = ["USD", "EUR", "RUB", "PLN"]
        found = {}
        for row in data:
            code = row.get("Cur_Abbreviation")
            if code in wanted:
                scale = float(row.get("Cur_Scale") or 1)
                rate = float(row.get("Cur_OfficialRate") or 0)
                if rate and scale:
                    found[code] = (rate, int(scale))
                    if row.get("Date"):
                        result["date"] = str(row["Date"])[:10]
        result["fiat"] = [(c, found[c][0], found[c][1]) for c in wanted if c in found]

    data = http_json("https://api.coingecko.com/api/v3/simple/price"
                     "?ids=bitcoin,ethereum&vs_currencies=usd")
    if isinstance(data, dict):
        for key, label in (("bitcoin", "BTC"), ("ethereum", "ETH")):
            usd = (data.get(key) or {}).get("usd")
            if usd:
                result["crypto"].append((label, float(usd)))

    if not result["fiat"] and not result["crypto"]:
        return None
    return result


def fmt_num(value, digits=2):
    text = f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")
    return text


def rates_lines(rates):
    """Строки для поста: (фиатная строка, крипто-строка)."""
    if not rates:
        return [], []
    fiat, crypto = [], []
    for code, value, scale in rates.get("fiat", []):
        if scale > 1:
            fiat.append(f"{scale} {code} {fmt_num(value)}")
        else:
            fiat.append(f"{code} {fmt_num(value)}")
    for code, value in rates.get("crypto", []):
        crypto.append(f"{code} ${fmt_num(value, 0)}")
    return fiat, crypto


# -------------------------------------------------------------------- cover
def _font(size, bold=True):
    names = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf"] if bold else ["DejaVuSans.ttf"]
    roots = ["/usr/share/fonts/truetype/dejavu/", "/usr/share/fonts/TTF/",
             "/usr/share/fonts/truetype/liberation/", "/System/Library/Fonts/"]
    for root in roots:
        for name in names:
            path = os.path.join(root, name)
            if os.path.exists(path):
                return _load(path, size)
    try:
        from PIL import ImageFont
        return ImageFont.load_default(size)
    except Exception:  # noqa: BLE001
        return None


def _load(path, size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default(size)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def draw_icon(draw, kind, cx, cy, size, alpha=255):
    """Простые иконки погоды, нарисованные примитивами."""
    s = size / 2.0
    sun = (255, 205, 90, alpha)
    cloud = (214, 221, 240, alpha)
    blue = (130, 170, 240, alpha)
    white = (255, 255, 255, alpha)
    # облако как 3 круга + основание
    def cloud_shape(dy=0):
        r1, r2, r3 = s * 0.34, s * 0.44, s * 0.30
        draw.ellipse([cx - r1 * 1.6, cy - r1 + dy - 6, cx + r1 * 0.2, cy + r1 + dy - 6], fill=cloud)
        draw.ellipse([cx - r2 * 0.55, cy - r2 + dy - 16, cx + r2 * 1.15, cy + r2 + dy - 16], fill=cloud)
        draw.ellipse([cx + r2 * 0.1, cy - r3 + dy - 4, cx + r3 * 2.0, cy + r3 + dy - 4], fill=cloud)
        draw.rounded_rectangle([cx - r1 * 1.6, cy + dy - 14, cx + r3 * 2.0, cy + r1 * 0.55 + dy],
                               radius=int(s * 0.18), fill=cloud)

    if kind == "sun":
        draw.ellipse([cx - s * 0.42, cy - s * 0.42, cx + s * 0.42, cy + s * 0.42], fill=sun)
        for i in range(8):
            ang = i * math.pi / 4
            x1, y1 = cx + math.cos(ang) * s * 0.58, cy + math.sin(ang) * s * 0.58
            x2, y2 = cx + math.cos(ang) * s * 0.86, cy + math.sin(ang) * s * 0.86
            draw.line([x1, y1, x2, y2], fill=sun, width=max(3, int(s * 0.09)))
    elif kind == "partly":
        draw.ellipse([cx - s * 0.72, cy - s * 0.72, cx + s * 0.02, cy + s * 0.02], fill=sun)
        for i in range(8):
            ang = i * math.pi / 4
            x1, y1 = cx - s * 0.35 + math.cos(ang) * s * 0.5, cy - s * 0.35 + math.sin(ang) * s * 0.5
            x2, y2 = cx - s * 0.35 + math.cos(ang) * s * 0.72, cy - s * 0.35 + math.sin(ang) * s * 0.72
            draw.line([x1, y1, x2, y2], fill=sun, width=max(2, int(s * 0.07)))
        cloud_shape(dy=int(s * 0.30))
    elif kind in ("cloud", "fog"):
        cloud_shape(dy=-int(s * 0.05))
        if kind == "fog":
            for i in range(3):
                y = cy + s * (0.55 + i * 0.16)
                draw.line([cx - s * 0.8, y, cx + s * 0.8, y], fill=cloud, width=max(3, int(s * 0.07)))
    elif kind == "rain":
        cloud_shape(dy=-int(s * 0.12))
        for i in range(3):
            x = cx - s * 0.45 + i * s * 0.42
            draw.line([x, cy + s * 0.55, x - s * 0.12, cy + s * 0.95], fill=blue,
                      width=max(3, int(s * 0.09)))
    elif kind == "snow":
        cloud_shape(dy=-int(s * 0.12))
        for i in range(3):
            x = cx - s * 0.45 + i * s * 0.42
            y = cy + s * 0.78
            r = s * 0.11
            for ang in (0, math.pi / 3, 2 * math.pi / 3):
                draw.line([x - math.cos(ang) * r, y - math.sin(ang) * r,
                           x + math.cos(ang) * r, y + math.sin(ang) * r], fill=white, width=2)
    elif kind == "storm":
        cloud_shape(dy=-int(s * 0.15))
        draw.polygon([(cx + s * 0.05, cy + s * 0.30), (cx - s * 0.30, cy + s * 1.0),
                      (cx - s * 0.02, cy + s * 1.0), (cx - s * 0.18, cy + s * 1.35),
                      (cx + s * 0.42, cy + s * 0.62), (cx + s * 0.10, cy + s * 0.62)],
                     fill=(255, 210, 90, alpha))


def draw_cover(now, weather, path="cover.png", width=1280, height=720):
    """Обложка выпуска: дата, погода Гродно, фирменный фон."""
    from PIL import Image, ImageDraw, ImageFilter

    day = now.astimezone(TZ)
    img = Image.new("RGB", (width, height), (14, 12, 32))
    draw = ImageDraw.Draw(img)

    top, mid, bottom = (13, 11, 30), (58, 26, 62), (128, 56, 60)
    for y in range(height):
        t = y / (height - 1)
        if t < 0.62:
            color = _lerp(top, mid, t / 0.62)
        else:
            color = _lerp(mid, bottom, (t - 0.62) / 0.38)
        draw.line([0, y, width, y], fill=color)

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([width * 0.55, -height * 0.4, width * 1.25, height * 1.1],
               fill=(255, 170, 90, 55))
    gd.ellipse([-width * 0.25, height * 0.5, width * 0.45, height * 1.4],
               fill=(255, 120, 120, 30))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    draw = ImageDraw.Draw(img)

    # декоративные кольца
    ring = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse([width * 0.62, height * 0.45, width * 0.95, height * 1.15],
               outline=(255, 220, 170, 26), width=28)
    rd.ellipse([width * 0.30, -height * 0.25, width * 0.52, height * 0.22],
               outline=(255, 220, 170, 18), width=18)
    img = Image.alpha_composite(img, ring)
    draw = ImageDraw.Draw(img)

    white = (255, 250, 242)
    accent = (255, 209, 102)
    muted = (240, 226, 226)

    f_kicker = _font(int(height * 0.055), True)
    f_title = _font(int(height * 0.115), True)
    f_date = _font(int(height * 0.155), True)
    f_sub = _font(int(height * 0.052), False)
    f_temp = _font(int(height * 0.20), True)
    f_desc = _font(int(height * 0.048), False)
    f_foot = _font(int(height * 0.036), False)

    left = int(width * 0.065)
    draw.text((left, int(height * 0.10)), "В Е Л О Д А Й Д Ж Е С Т", font=f_kicker, fill=accent)
    draw.text((left, int(height * 0.155)), "БЕЛАРУСИ", font=f_title, fill=white)
    draw.text((left, int(height * 0.47)), f"{day.day} {MONTHS[day.month - 1].upper()}",
              font=f_date, fill=white)
    draw.text((left, int(height * 0.68)), f"{WEEKDAYS[day.weekday()]} · Гродно",
              font=f_sub, fill=muted)

    draw.line([left, int(height * 0.80), int(width * 0.42), int(height * 0.80)],
              fill=(255, 255, 255, 90), width=3)

    if weather:
        cx, cy = int(width * 0.84), int(height * 0.34)
        draw_icon(draw, weather["icon"], cx, cy, int(height * 0.30))
        draw.text((int(width * 0.74), int(height * 0.53)), f"{weather['temp']:+d}°",
                  font=f_temp, fill=accent)
        desc = weather["desc"]
        draw.text((int(width * 0.75), int(height * 0.76)), desc, font=f_desc, fill=muted)

    draw.text((left, int(height * 0.87)), "Хороших новостей и попутного ветра",
              font=f_foot, fill=(235, 225, 220))

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.convert("RGB").save(path, "PNG")
    return path
