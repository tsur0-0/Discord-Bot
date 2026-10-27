"""Geração de imagens com Pillow: cartão de perfil e painel estilo inventário."""
import io
import os
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


FONT_CANDIDATES = [
    os.path.join(ASSETS, "fonts", "minecraft.ttf"),  # opcional: coloque sua fonte aqui (ex.: Minecraftia)
    os.path.join(ASSETS, "fonts", "fallback.ttf"),   # DejaVu Sans Bold (suporta acentos)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


@lru_cache(maxsize=32)
def font(size: int):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size=size)  # atenção: sem acentos
    except TypeError:
        return ImageFont.load_default()


def text(d, xy, s, f, fill=(255, 255, 255), shadow=(25, 25, 25), anchor="la"):
    x, y = xy
    if shadow:
        d.text((x + 2, y + 2), s, font=f, fill=shadow, anchor=anchor)
    d.text((x, y), s, font=f, fill=fill, anchor=anchor)


def fit(d, s, f, maxw):
    if d.textlength(s, font=f) <= maxw:
        return s
    while s and d.textlength(s + "…", font=f) > maxw:
        s = s[:-1]
    return s + "…"


def wrap(d, s, f, maxw, maxlines=2):
    lines, cur = [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return [fit(d, l, f, maxw) for l in lines[:maxlines]]


def stone(w, h, base=(58, 58, 64), seed=7, tile=8):
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), base)
    d = ImageDraw.Draw(img)
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            k = rnd.randint(-14, 14)
            d.rectangle([x, y, x + tile - 1, y + tile - 1],
                        fill=tuple(max(0, min(255, v + k)) for v in base))
    return img


def _buf(img):
    b = io.BytesIO()
    img.save(b, "PNG")
    b.seek(0)
    return b


# --------------------------------------------------------------------------
# Cartão de perfil
# --------------------------------------------------------------------------
def render_profile_card(avatar_bytes, name, joined, level, progress, needed, rank,
                        xp, bio, title, accent, stats):
    W, H = 900, 340
    img = stone(W, H)
    d = ImageDraw.Draw(img)
    d.rectangle([14, 14, W - 15, H - 15], fill=(22, 22, 26), outline=accent, width=4)

    av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    av = av.resize((32, 32), Image.BILINEAR).resize((160, 160), Image.NEAREST)  # avatar "pixelado"
    d.rectangle([34, 34, 206, 206], fill=(10, 10, 10), outline=accent, width=4)
    img.paste(av, (40, 40), av)

    x0, maxw = 235, W - 235 - 150
    text(d, (x0, 30), fit(d, name, font(40), maxw), font(40))
    if title:
        text(d, (x0, 82), fit(d, title, font(22), maxw), font(22), fill=accent)
    text(d, (x0, 112), f"Entrou em: {joined}", font(18), fill=(190, 190, 190))
    for i, line in enumerate(wrap(d, bio, font(18), W - x0 - 40, 2)):
        text(d, (x0, 142 + i * 26), line, font(18), fill=(230, 230, 230), shadow=None)

    text(d, (W - 40, 30), f"#{rank}", font(44), fill=(255, 215, 90), anchor="ra")
    text(d, (W - 40, 82), "RANKING", font(16), fill=(170, 170, 170), anchor="ra")

    text(d, (40, 212), f"NÍVEL {level}", font(24), fill=accent)
    text(d, (W - 40, 214), f"{progress} / {needed} XP", font(20), anchor="ra")
    filled = round(40 * progress / needed) if needed else 0
    for i in range(40):  # barra de XP segmentada
        x = 40 + int(i * 20.5)
        d.rectangle([x, 246, x + 18, 274], fill=accent if i < filled else (50, 50, 56))
        if i < filled:
            d.rectangle([x, 246, x + 18, 251], fill=tuple(min(255, c + 45) for c in accent))
    text(d, (40, 292), "   •   ".join(f"{k}: {v}" for k, v in stats.items()),
         font(19), fill=(200, 200, 200), shadow=None)
    return _buf(img)


# --------------------------------------------------------------------------
# Painel estilo inventário
# --------------------------------------------------------------------------
def draw_icon(img, d, key, x, y, s=64):
    p = os.path.join(ASSETS, "icons", f"{key}.png")  # ícones próprios substituem os desenhados
    if os.path.exists(p):
        ic = Image.open(p).convert("RGBA").resize((s - 12, s - 12), Image.NEAREST)
        img.paste(ic, (x + 6, y + 6), ic)
        return
    m = 8
    u = (s - 2 * m) / 8

    def R(a, b, c, e, col):
        d.rectangle([x + m + a * u, y + m + b * u, x + m + c * u - 1, y + m + e * u - 1], fill=col)

    def P(pts, col):
        d.polygon([(x + m + a * u, y + m + b * u) for a, b in pts], fill=col)

    gray = (150, 150, 160)
    if key == "home":
        P([(0, 4), (4, 0), (8, 4)], (180, 50, 50))
        R(1, 4, 7, 8, (150, 100, 60))
        R(3, 5, 5, 8, (90, 60, 30))
    elif key in ("profile", "member"):
        R(2, 0, 6, 4, (224, 172, 130))
        R(2, 4, 6, 8, (60, 100, 190))
        R(3, 2, 4, 3, (60, 40, 30))
        R(4, 2, 5, 3, (60, 40, 30))
    elif key == "mod":
        d.line([(x + m + 7 * u, y + m + 1 * u), (x + m + 2.5 * u, y + m + 5.5 * u)],
               fill=(225, 225, 235), width=int(u * 1.8))
        d.line([(x + m + 1.5 * u, y + m + 4.5 * u), (x + m + 4.5 * u, y + m + 7.5 * u)],
               fill=(220, 170, 40), width=int(u * 1.2))
        R(0, 7, 2, 8, (110, 70, 30))
    elif key == "roles":
        P([(1, 0), (7, 0), (7, 4), (4, 8), (1, 4)], gray)
        P([(2, 1), (6, 1), (6, 4), (4, 7), (2, 4)], (220, 170, 40))
    elif key == "logs":
        R(1, 0, 7, 8, (120, 70, 40))
        R(2, 1, 6, 7, (240, 230, 200))
        for yy in (2, 4, 6):
            R(3, yy, 5, yy + 1, (90, 90, 90))
    elif key == "config":
        R(3, 0, 5, 8, gray)
        R(0, 3, 8, 5, gray)
        d.ellipse([x + m + u, y + m + u, x + m + 7 * u, y + m + 7 * u], fill=(175, 175, 185))
        d.ellipse([x + m + 3 * u, y + m + 3 * u, x + m + 5 * u, y + m + 5 * u], fill=(60, 60, 65))
    elif key == "fun":
        P([(4, 0), (7, 3), (4, 8), (1, 3)], (80, 220, 210))
        P([(4, 1), (6, 3), (4, 6), (2, 3)], (150, 240, 235))
    elif key == "tnt":
        R(0, 1, 8, 7, (200, 40, 40))
        R(0, 3, 8, 5, (235, 235, 235))
    else:
        R(1, 1, 7, 7, (120, 120, 120))


def _short(n):
    n = int(n)
    return f"{n/1000:.1f}k" if n >= 10000 else str(n)


def render_inventory(title, slots, selected=None, cols=9, rows=3, footer=""):
    """slots: lista de dicts {icon, label, count} (ou None para slot vazio)."""
    S, G, P = 64, 6, 18
    W = P * 2 + cols * (S + G) - G
    top = P + 34
    H = top + rows * (S + G) - G + P + 28
    img = Image.new("RGB", (W, H), (198, 198, 198))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline=(20, 20, 20), width=3)
    d.line([(3, 3), (W - 4, 3)], fill=(255, 255, 255), width=3)
    d.line([(3, 3), (3, H - 4)], fill=(255, 255, 255), width=3)
    text(d, (P, P), title, font(22), fill=(64, 64, 64), shadow=None)

    for idx in range(cols * rows):
        r, c = divmod(idx, cols)
        x, y = P + c * (S + G), top + r * (S + G)
        d.rectangle([x, y, x + S, y + S], fill=(139, 139, 139))
        d.line([(x, y), (x + S, y)], fill=(55, 55, 55), width=3)
        d.line([(x, y), (x, y + S)], fill=(55, 55, 55), width=3)
        d.line([(x, y + S), (x + S, y + S)], fill=(255, 255, 255), width=3)
        d.line([(x + S, y), (x + S, y + S)], fill=(255, 255, 255), width=3)
        item = slots[idx] if idx < len(slots) else None
        if item:
            draw_icon(img, d, item["icon"], x, y, S)
            if item.get("count") is not None:
                text(d, (x + S - 4, y + S - 4), _short(item["count"]), font(18), anchor="rd")
        if selected is not None and idx == selected:
            d.rectangle([x - 3, y - 3, x + S + 3, y + S + 3], outline=(255, 200, 40), width=4)

    label = footer
    if not label and selected is not None and selected < len(slots) and slots[selected]:
        label = slots[selected]["label"]
    text(d, (P, H - P - 18), label, font(18), fill=(64, 64, 64), shadow=None)
    return _buf(img)
