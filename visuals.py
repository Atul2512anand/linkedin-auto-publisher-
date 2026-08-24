import os
import random
import re
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

from common import BASE_DIR, DRAFTS_DIR, load_env

W, H = 1080, 1350
BG_TOP = (10, 16, 30)
BG_BOT = (22, 34, 56)
TEXT_MAIN = (240, 244, 250)
TEXT_DIM = (148, 163, 184)
DEFAULT_ACCENT = (34, 211, 238)

FONT_DIRS = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
FONT_BOLD_CANDIDATES = ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf"]
FONT_REG_CANDIDATES = ["segoeui.ttf", "arial.ttf", "calibri.ttf"]


def _accent_color():
    load_env()
    raw = os.environ.get("ACCENT_COLOR", "#22D3EE").strip().lstrip("#")
    try:
        return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return DEFAULT_ACCENT


def _brand():
    load_env()
    return os.environ.get("BRAND_NAME", "").strip()


def _font(candidates, size):
    for directory in FONT_DIRS:
        for name in candidates:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _canvas(accent):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        color = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=color)
    draw.rectangle([0, 0, 18, H], fill=accent)
    return img, draw


def _kicker(draw, accent):
    brand = _brand() or "TECH INSIGHTS"
    font = _font(FONT_REG_CANDIDATES, 30)
    draw.text((70, 60), brand.upper(), font=font, fill=accent)


def _footer(draw, index, total, accent):
    font = _font(FONT_REG_CANDIDATES, 28)
    dots_x = 70
    for i in range(total):
        color = accent if i == index - 1 else TEXT_DIM
        draw.ellipse([dots_x, H - 80, dots_x + 14, H - 66], fill=color)
        dots_x += 26
    draw.text((W - 160, 52), f"{index}/{total}", font=font, fill=TEXT_DIM)


def parse_post(text):
    lines = [ln.strip() for ln in text.splitlines()]
    content = []
    for ln in lines:
        if not ln:
            continue
        if ln.startswith("# Topic:"):
            continue
        if ln.startswith("#"):
            continue
        if ln.startswith("#") and " " not in ln.replace("#", "")[:40]:
            continue
        if ln.lower().startswith("source:"):
            continue
        content.append(ln.strip())

    def clean(ln):
        return re.sub(r"\*\*|__|[*_`]", "", ln).strip()

    hook = clean(content[0]) if content else "Quick tech insight"
    points = []
    cta = None
    for ln in content[1:]:
        cl = clean(ln)
        bullet = re.match(r"^(?:[-–—•→*]|\d+[.)])\s+(.*)$", cl)
        if bullet:
            points.append(bullet.group(1).strip())
        elif "?" in cl and len(cl) < 200:
            cta = cl
    if len(points) < 3:
        for ln in content[1:]:
            cl = clean(ln)
            if cl in points or cl == cta or len(cl) > 170:
                continue
            if re.match(r"^(?:[-–—•→*]|\d+[.)])", ln.strip()):
                continue
            points.append(cl)
    points = points[:4]
    if not cta:
        cta = "What's your take on this?"
    return {"hook": hook, "points": points, "cta": cta}


def _slide_cover(parsed, total, accent):
    img, draw = _canvas(accent)
    _kicker(draw, accent)
    font = _font(FONT_BOLD_CANDIDATES, 84)
    lines = _wrap(draw, parsed["hook"], font, W - 200)[:7]
    y = 300
    for line in lines:
        draw.text((70, y), line, font=font, fill=TEXT_MAIN)
        y += int(font.size * 1.18)
    hint_font = _font(FONT_REG_CANDIDATES, 40)
    draw.text((70, H - 180), "swipe →", font=hint_font, fill=accent)
    _footer(draw, 1, total, accent)
    return img


def _slide_point(point, idx, total, accent):
    img, draw = _canvas(accent)
    _kicker(draw, accent)
    num_font = _font(FONT_BOLD_CANDIDATES, 120)
    draw.text((66, 130), str(idx), font=num_font, fill=accent)
    font = _font(FONT_BOLD_CANDIDATES, 58)
    body = point[:230]
    lines = _wrap(draw, body, font, W - 210)[:8]
    y = 380
    for line in lines:
        draw.text((70, y), line, font=font, fill=TEXT_MAIN)
        y += int(font.size * 1.25)
    _footer(draw, idx + 1, total, accent)
    return img


def _slide_cta(cta, total, accent):
    img, draw = _canvas(accent)
    _kicker(draw, accent)
    label_font = _font(FONT_REG_CANDIDATES, 36)
    draw.text((70, 260), "YOUR MOVE", font=label_font, fill=accent)
    font = _font(FONT_BOLD_CANDIDATES, 64)
    lines = _wrap(draw, cta[:220], font, W - 210)[:6]
    y = 420
    for line in lines:
        draw.text((70, y), line, font=font, fill=TEXT_MAIN)
        y += int(font.size * 1.25)
    brand = _brand()
    if brand:
        bfont = _font(FONT_REG_CANDIDATES, 32)
        draw.text((70, H - 150), f"— {brand}", font=bfont, fill=TEXT_DIM)
    _footer(draw, total, total, accent)
    return img


def build_carousel(text, out_dir=None):
    load_env()
    out_dir = out_dir or os.path.join(DRAFTS_DIR, "assets")
    os.makedirs(out_dir, exist_ok=True)
    accent = _accent_color()
    parsed = parse_post(text)
    total = 2 + len(parsed["points"])
    slides = [_slide_cover(parsed, total, accent)]
    for i, point in enumerate(parsed["points"], start=1):
        slides.append(_slide_point(point, i, total, accent))
    slides.append(_slide_cta(parsed["cta"], total, accent))
    total = len(slides)

    stamp = f"carousel_{random.randint(1000, 9999)}"
    pdf_path = os.path.join(out_dir, f"{stamp}.pdf")
    first, rest = slides[0], slides[1:]
    first.save(pdf_path, save_all=True, append_images=rest, resolution=96)
    pngs = []
    for i, slide in enumerate(slides, start=1):
        p = os.path.join(out_dir, f"{stamp}_slide{i}.png")
        slide.save(p)
        pngs.append(p)
    return pdf_path, pngs


def build_hero(text):
    load_env()
    out_dir = os.path.join(DRAFTS_DIR, "assets")
    os.makedirs(out_dir, exist_ok=True)
    parsed = parse_post(text)
    hook = re.sub(r"[^\w\s.,:!?\-]", "", parsed["hook"])[:120]
    prompt = (
        f"Professional dark tech editorial illustration about: {hook}. "
        "Deep navy blue background with glowing cyan circuit patterns, abstract "
        "network nodes, subtle depth of field, minimal, modern, no text, "
        "editorial magazine cover style"
    )
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + "?width=1200&height=627&nologo=true&seed="
        + str(random.randint(1, 999999))
    )
    resp = requests.get(url, timeout=180)
    resp.raise_for_status()
    path = os.path.join(out_dir, f"hero_{random.randint(1000, 9999)}.png")
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


if __name__ == "__main__":
    import sys

    sample = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else (
        "Your API keys are leaking right now.\n\n"
        "- Scan repos weekly for hardcoded secrets\n"
        "- Rotate credentials every quarter minimum\n"
        "- Use a vault, never environment dumps\n"
        "- Alert on unusual key usage patterns\n\n"
        "When did you last audit your keys?\n\n"
        "#Cybersecurity #DevSecOps"
    )
    pdf, pngs = build_carousel(sample)
    print(f"PDF: {pdf}")
    for p in pngs:
        print(f"PNG: {p}")
