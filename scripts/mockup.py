#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Макет: как будет выглядеть пост в Telegram (приблизительно, без обложки)."""
import os
import sys
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H = 1080, 1440
BG_TOP, BG_BOTTOM = (14, 22, 33), (10, 15, 23)
BUBBLE = (24, 37, 51)
TEXT = (255, 255, 255)
MUTED = (125, 139, 153)
LINK = (100, 181, 239)
LINE = (43, 58, 74)
ACCENT = (255, 209, 102)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_I = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"


def font(size, kind="r"):
    path = {"r": FONT, "b": FONT_B, "i": FONT_I}[kind]
    return ImageFont.truetype(path, size)


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for word in words:
        probe = (cur + " " + word).strip()
        if draw.textlength(probe, font=fnt) <= max_w:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, text, fnt, color, x, y, max_w, gap=8, after=14):
    for line in wrap(draw, text, fnt, max_w):
        draw.text((x, y), line, font=fnt, fill=color)
        y += fnt.size + gap
    return y + after


def main():
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([0, y, W, y], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 92], fill=(23, 33, 43))
    d.text((W // 2, 46), "GrodnoBikeClub", font=font(30, "b"), fill=TEXT, anchor="mm")
    d.text((W // 2, 78), "канал · 12 ноября", font=font(20), fill=MUTED, anchor="mm")

    bx, by, bw = 70, 120, 940
    bubble_h = 1150
    d.rounded_rectangle([bx, by, bx + bw, by + bubble_h], radius=28, fill=BUBBLE)

    x = bx + 36
    max_w = bw - 72
    y = by + 34

    y = text_block(d, "Новости для нас", font(46, "b"), TEXT, x, y, max_w, gap=6, after=8)
    y = text_block(d, "12 ноября, четверг · Гродно, +2°, облачно · 7 новостей",
                   font(26), MUTED, x, y, max_w, gap=4, after=18)

    quote = "Только хорошие новости: велоспорт Беларуси и жизнь Гродно. Без политики и происшествий."
    qf = font(27, "i")
    qlines = wrap(d, quote, qf, max_w - 30)
    qh = len(qlines) * (qf.size + 8)
    d.rounded_rectangle([x, y, x + 6, y + qh], radius=3, fill=ACCENT)
    qy = y
    for line in qlines:
        d.text((x + 24, qy), line, font=qf, fill=(226, 232, 240))
        qy += qf.size + 8
    y = qy + 20

    d.line([x, y, x + max_w, y], fill=LINE, width=2)
    y += 24

    items = [
        ("Кубок Беларуси по велотреку: яркие финалы", "Sport5.by",
         "В Минске определились победители — зрелищные заезды и новые рекорды."),
        ("Велопробег в Гродно собрал сотни участников", "Гродно 24",
         "Городской праздник спорта прошёл на набережной Немана."),
        ("Юная велогонщица из Бреста — призёр международной гонки", "БелТА",
         "Наша спортсменка поднялась на пьедестал в Италии."),
    ]

    for index, (title, source, summary) in enumerate(items, 1):
        y = text_block(d, f"{index}. {title}", font(32, "b"), TEXT, x, y, max_w, gap=6, after=8)
        y = text_block(d, summary, font(27), (200, 210, 220), x, y, max_w, gap=6, after=6)
        d.text((x, y), f"→ {source}", font=font(26), fill=LINK)
        y += 34 + 18

    d.line([x, y, x + max_w, y], fill=LINE, width=2)
    y += 24

    d.text((x, y), "USD 3,01 · EUR 3,35 · 100 RUB 3,64 · 10 PLN 7,61", font=font(25), fill=(226, 232, 240))
    y += 38
    d.text((x, y), "BTC $73 461 · ETH $2 047", font=font(25), fill=(226, 232, 240))
    y += 46

    d.text((x, y), "Хорошего дня и попутного ветра!", font=font(25), fill=MUTED)
    y += 38
    d.text((x, y), "#Гродно", font=font(25), fill=LINK)
    y += 40
    d.text((x, y), "@GrodnoBikeClub", font=font(27, "b"), fill=LINK)

    d.rectangle([0, H - 86, W, H], fill=(23, 33, 43))
    d.rounded_rectangle([70, H - 66, W - 70, H - 20], radius=23, fill=(30, 42, 56))
    d.text((100, H - 43), "Сообщение", font=font(24), fill=(110, 125, 140), anchor="lm")

    img.save("mockup.png")
    print("saved mockup.png")


if __name__ == "__main__":
    main()
