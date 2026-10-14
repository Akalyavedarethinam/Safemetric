"""
Render a synthetic label record into a product-label photograph-like image with exact
word / line annotations, then apply realistic capture degradations.

Coordinates of every word are tracked through the whole process:
    label canvas  ->  scene canvas (offset)  ->  homography (rotation + perspective)
                  ->  optional crop (partial visibility)  ->  final resize
so the ground-truth quads always match the pixels of the saved image.
"""
from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

# family -> (regular, bold, has_rupee, has_devanagari)
FONTS = {
    "DejaVuSans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", True, False),
    "DejaVuSansCondensed": ("DejaVuSansCondensed.ttf", "DejaVuSansCondensed-Bold.ttf", True, False),
    "DejaVuSerif": ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", True, False),
    "LiberationSans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", False, False),
    "LiberationSerif": ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", False, False),
    "Carlito": ("Carlito-Regular.ttf", "Carlito-Bold.ttf", True, False),
    "Poppins": ("Poppins-Regular.ttf", "Poppins-Bold.ttf", True, True),
    "FreeSans": ("FreeSans.ttf", "FreeSansBold.ttf", True, True),
    "TeXGyreHeros": ("texgyreheros-regular.otf", "texgyreheros-bold.otf", False, False),
    "TeXGyreHerosCn": ("texgyreheroscn-regular.otf", "texgyreheroscn-bold.otf", False, False),
    # held-out families: used ONLY in the test split (measures generalisation to unseen typefaces)
    "TeXGyreAdventor": ("texgyreadventor-regular.otf", "texgyreadventor-bold.otf", False, False),
    "Caladea": ("Caladea-Regular.ttf", "Caladea-Bold.ttf", False, False),
    "Lora": ("Lora-Variable.ttf", "Lora-Variable.ttf", False, False),
}
MONO_FONTS = {"DejaVuSansMono": "DejaVuSansMono.ttf", "LiberationMono": "LiberationMono-Regular.ttf"}
HELDOUT_FAMILIES = {"TeXGyreAdventor", "Caladea", "Lora"}
TRAIN_FAMILIES = [f for f in FONTS if f not in HELDOUT_FAMILIES]
DEVANAGARI_FALLBACK = "FreeSans"

LEGIBLE_CONTRAST = 7.0     # words whose box std-dev in the final image is lower are marked illegible ("don't care")
VISIBLE_THRESHOLD = 0.9   # a word counts as visible (and is part of the GT text) if >= 90 % of it is in frame
SIZE_MULT = {"xxl": 2.6, "xl": 2.0, "l": 1.5, "m": 1.15, "s": 0.92, "xs": 0.78}

LIGHT_BG = [(250, 250, 248), (255, 253, 240), (252, 246, 228), (245, 240, 225), (236, 246, 236), (232, 242, 252),
            (255, 248, 220), (248, 238, 238), (240, 240, 240), (225, 210, 180)]
DARK_BG = [(20, 40, 90), (18, 70, 40), (110, 20, 30), (25, 25, 25), (60, 30, 80), (0, 80, 90), (90, 50, 10)]
MID_BG = [(230, 120, 30), (40, 150, 70), (200, 40, 50), (30, 110, 190), (240, 190, 40), (140, 80, 160), (0, 150, 150)]
DARK_TEXT = [(15, 15, 15), (30, 30, 30), (10, 30, 80), (20, 70, 30), (100, 20, 20), (60, 40, 20)]
LIGHT_TEXT = [(255, 255, 255), (250, 245, 225), (255, 230, 120), (230, 240, 255)]


@lru_cache(maxsize=512)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / path), size=size, layout_engine=ImageFont.Layout.RAQM)


@lru_cache(maxsize=128)
def _variable_font(path: str, size: int, instance: str) -> ImageFont.FreeTypeFont:
    """Variable fonts get their own object per named instance: mutating a shared cached font would make
    the output depend on generation order (and break byte-identical regeneration)."""
    f = ImageFont.truetype(str(FONT_DIR / path), size=size, layout_engine=ImageFont.Layout.RAQM)
    try:
        f.set_variation_by_name(instance)
    except Exception:
        pass
    return f


def font_for(family: str, bold: bool, size: int) -> ImageFont.FreeTypeFont:
    reg, bld, *_ = FONTS[family]
    if family == "Lora":
        return _variable_font(reg, size, "Bold" if bold else "Regular")
    return _font(bld if bold else reg, size)


def has_devanagari(t: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in t)


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


# ============================================================================ text placement
@dataclass
class Word:
    text: str
    box: tuple  # x0, y0, x1, y1 in label canvas coordinates


@dataclass
class PlacedLine:
    text: str
    fields: list
    size: str
    lang: str
    dotmatrix: bool
    words: list = field(default_factory=list)
    kv_part: str | None = None
    wrapped: bool = False


class LabelPainter:
    """Draws lines word by word and records exact word boxes."""

    def __init__(self, img: Image.Image, rng: random.Random, family: str, display_family: str, base: int):
        self.img, self.draw, self.rng = img, ImageDraw.Draw(img), rng
        self.family, self.display_family, self.base = family, display_family, base
        self.lines: list[PlacedLine] = []

    def _fam(self, text: str, display: bool) -> str:
        fam = self.display_family if display else self.family
        if has_devanagari(text) and not FONTS[fam][3]:
            return DEVANAGARI_FALLBACK
        return fam

    def fit_text(self, text: str, fam: str) -> str:
        if "₹" in text and not FONTS[fam][2]:
            text = text.replace("₹ ", "Rs. ").replace("₹", "Rs.")
        return text

    def measure(self, text, font):
        return font.getlength(text)

    def draw_line(self, spec: dict, x: float, y: float, width: float, color, align="left",
                  display=False, dot_color=None, kv_part=None) -> float:
        """Draw (and wrap) a line starting at top y. Returns the new y below it."""
        size = max(9, int(round(self.base * SIZE_MULT[spec["size"]])))
        fam = self._fam(spec["text"], display)
        text = self.fit_text(spec["text"], fam)
        if spec.get("dotmatrix"):
            font = _font(MONO_FONTS[self.rng.choice(list(MONO_FONTS))], size)
        else:
            font = font_for(fam, spec.get("bold", False), size)
        words = text.split()
        space = font.getlength(" ")
        # wrap
        rows, cur = [], []
        for w in words:
            trial = " ".join(cur + [w])
            if cur and font.getlength(trial) > width:
                rows.append(cur)
                cur = [w]
            else:
                cur.append(w)
        if cur:
            rows.append(cur)
        ascent, descent = font.getmetrics()
        line_h = ascent + descent
        # word boxes use a common vertical extent per line (ascender top .. descender bottom), the usual
        # convention of text-detection datasets, instead of the tight ink box of each word
        _, v_top, _, v_bot = font.getbbox("Hbdlfhkgjpqy|", anchor="ls")
        for ri, row in enumerate(rows):
            row_text = " ".join(row)
            tw = font.getlength(row_text)
            cx = x + (width - tw) / 2 if align == "center" else x
            baseline = y + ascent
            pl = PlacedLine(row_text, spec["fields"], spec["size"], spec.get("lang", "en"), bool(spec.get("dotmatrix")),
                            kv_part=kv_part, wrapped=len(rows) > 1)
            if spec.get("dotmatrix"):
                self._dot_matrix_row(row, font, cx, baseline, dot_color or color, pl, space)
            else:
                for w in row:
                    ink = self.draw.textbbox((cx, baseline), w, font=font, anchor="ls")
                    self.draw.text((cx, baseline), w, font=font, fill=color, anchor="ls")
                    box = (ink[0], min(ink[1], baseline + v_top), ink[2], max(ink[3], baseline + v_bot))
                    pl.words.append(Word(w, box))
                    cx += font.getlength(w) + space
            self.lines.append(pl)
            y += line_h * (1.12 if ri < len(rows) - 1 else 1.0)
        return y

    def _dot_matrix_row(self, row, font, cx, baseline, color, pl, space):
        """Simulated ink-jet / dot-matrix print: glyph mask re-sampled on a coarse dot grid."""
        asc, desc = font.getmetrics()
        pitch = max(2, int(round((asc + desc) / 9)))
        r = max(1, int(round(pitch * 0.45)))
        for w in row:
            box = self.draw.textbbox((cx, baseline), w, font=font, anchor="ls")
            wimg = Image.new("L", (int(box[2] - box[0]) + 4, int(box[3] - box[1]) + 4), 0)
            ImageDraw.Draw(wimg).text((2 - (box[0] - cx), 2 - (box[1] - baseline)), w, font=font, fill=255, anchor="ls")
            arr = np.array(wimg)
            for yy in range(0, arr.shape[0], pitch):
                for xx in range(0, arr.shape[1], pitch):
                    if arr[yy:yy + pitch, xx:xx + pitch].mean() > 90:
                        px, py = box[0] - 2 + xx + pitch / 2, box[1] - 2 + yy + pitch / 2
                        self.draw.ellipse((px - r, py - r, px + r, py + r), fill=color)
            _, v_top, _, v_bot = font.getbbox("Hbdlfhkgjpqy|", anchor="ls")
            pl.words.append(Word(w, (box[0], min(box[1], baseline + v_top), box[2], max(box[3], baseline + v_bot))))
            cx += font.getlength(w) + space


# ============================================================================ label composition
def _choose_colors(rng: random.Random):
    style = rng.choices(["light", "dark", "mid", "low_contrast"], [0.58, 0.14, 0.14, 0.14])[0]
    if style == "light":
        bg, fg = rng.choice(LIGHT_BG), rng.choice(DARK_TEXT)
    elif style == "dark":
        bg, fg = rng.choice(DARK_BG), rng.choice(LIGHT_TEXT)
    elif style == "mid":
        bg = rng.choice(MID_BG)
        fg = (255, 255, 255) if _lum(bg) < 150 else (15, 15, 15)
    else:
        bg = rng.choice(LIGHT_BG)
        k = rng.uniform(0.45, 0.62)            # text only 38-55 % darker than the background
        fg = tuple(int(c * k) for c in bg)
    accent = rng.choice(MID_BG) if style in ("light", "low_contrast") else rng.choice(LIGHT_TEXT)
    return style, bg, fg, accent


def _free(box, text_boxes, pad=8) -> bool:
    x0, y0, x1, y1 = box
    return all(x1 + pad < b[0] or b[2] + pad < x0 or y1 + pad < b[1] or b[3] + pad < y0 for b in text_boxes)


def _decorate(img: Image.Image, rng: random.Random, accent, bg, occupied: list):
    """Non-text distractors: border, barcode, veg symbol. Never drawn over text (`occupied` = word boxes)."""
    d = ImageDraw.Draw(img)
    W, H = img.size
    if rng.random() < 0.5:
        m = rng.randint(6, 16)
        d.rectangle((m, m, W - m, H - m), outline=accent, width=rng.randint(2, 5))
    if rng.random() < 0.45:  # barcode in a free corner
        bw, bh = rng.randint(110, 170), rng.randint(50, 80)
        x0, y0 = W - bw - rng.randint(20, 40), H - bh - rng.randint(28, 50)
        if not _free((x0 - 6, y0 - 6, x0 + bw + 6, y0 + bh + 6), occupied):
            return _decorate_veg(d, rng, W, H, occupied)
        d.rectangle((x0 - 6, y0 - 6, x0 + bw + 6, y0 + bh + 6), fill=(255, 255, 255))
        xx = x0
        while xx < x0 + bw:
            w = rng.choice([1, 1, 2, 3])
            if rng.random() < 0.55:
                d.rectangle((xx, y0, xx + w - 1, y0 + bh), fill=(0, 0, 0))
            xx += w
        occupied.append((x0 - 6, y0 - 6, x0 + bw + 6, y0 + bh + 6))
    _decorate_veg(d, rng, W, H, occupied)


def _decorate_veg(d, rng, W, H, occupied):
    if rng.random() < 0.25:  # veg symbol
        s = rng.randint(22, 34)
        x0, y0 = W - s - rng.randint(18, 40), rng.randint(18, 40)
        if not _free((x0, y0, x0 + s, y0 + s), occupied):
            return
        d.rectangle((x0, y0, x0 + s, y0 + s), outline=(0, 140, 0), width=3)
        d.ellipse((x0 + s * 0.25, y0 + s * 0.25, x0 + s * 0.75, y0 + s * 0.75), fill=(0, 140, 0))
        occupied.append((x0, y0, x0 + s, y0 + s))


def render_label(rec: dict, rng: random.Random, heldout_fonts: bool) -> tuple[Image.Image, list[PlacedLine], dict]:
    fams = sorted(HELDOUT_FAMILIES) if heldout_fonts else list(TRAIN_FAMILIES)
    family = rng.choice(fams)
    display_family = rng.choice(fams) if rng.random() < 0.5 else family
    layout = rng.choices(["full_label", "two_panel", "back_panel", "front_panel", "table", "centered"],
                         [0.30, 0.18, 0.20, 0.10, 0.12, 0.10])[0]
    base = rng.randint(19, 30)
    style, bg, fg, accent = _choose_colors(rng)
    front, back = rec["panels"]["front"], rec["panels"]["back"]
    watermark = {"text": "SYNTHETIC SAMPLE - NOT A REAL PRODUCT", "fields": ["watermark"], "size": "xs", "bold": False}

    col_w = rng.randint(520, 760)
    if layout == "two_panel":
        W = 2 * col_w + 3 * 40
    else:
        W = col_w + 2 * 45
    H = 3000  # cropped later to the used height
    img = Image.new("RGB", (W, H), bg)
    p = LabelPainter(img, rng, family, display_family, base)
    occupied: list = []
    top = rng.randint(30, 55)

    def header_band(y, x0, x1, n_lines_h):
        if rng.random() < 0.4 and style in ("light", "low_contrast"):
            ImageDraw.Draw(img).rectangle((x0, y - 10, x1, y + n_lines_h + 12), fill=accent)
            return (255, 255, 255) if _lum(accent) < 150 else (15, 15, 15)
        return None

    def draw_front(x, y, w, align):
        brand_h = int(base * SIZE_MULT[front[0]["size"]] * 1.3)
        band_fg = header_band(y, x - 20, x + w + 20, brand_h)
        for i, spec in enumerate(front):
            color = band_fg if (i == 0 and band_fg) else (accent if (i == 0 and style == "light" and rng.random() < 0.4) else fg)
            y = p.draw_line(spec, x, y, w, color, align, display=spec["field"] in ("brand_name", "product_name"))
            y += base * rng.uniform(0.35, 0.9)
            if i == 0 and band_fg:
                y += 14
        return y

    def draw_back(x, y, w, as_table=False):
        for spec in back:
            if as_table and spec.get("kv") and rng.random() < 0.9:
                key, val = spec["kv"]
                kw = w * 0.38
                d = ImageDraw.Draw(img)
                y0 = y - 4
                ky = p.draw_line({**spec, "text": key, "dotmatrix": False, "bold": True}, x + 6, y, kw - 12, fg, kv_part="key")
                vy = p.draw_line({**spec, "text": val}, x + kw + 6, y, w - kw - 12, fg, kv_part="value")
                y = max(ky, vy) + 4
                d.rectangle((x, y0, x + w, y), outline=fg, width=1)
                d.line((x + kw, y0, x + kw, y), fill=fg, width=1)
                y += 2
            else:
                y = p.draw_line(spec, x, y, w, fg)
                y += base * rng.uniform(0.18, 0.5)
        return y

    margin = 45
    if layout == "two_panel":
        y1 = draw_front(40, top, col_w, rng.choice(["left", "center"]))
        x2 = 40 * 2 + col_w
        ImageDraw.Draw(img).line((x2 - 20, 20, x2 - 20, max(y1, 900)), fill=fg, width=1)
        y2 = draw_back(x2, top, col_w)
        y = max(y1, y2)
    elif layout == "front_panel":
        y = draw_front(margin, top + 20, col_w, rng.choice(["left", "center"]))
        y += 40
    elif layout == "back_panel":
        y = draw_back(margin, top, col_w)
    elif layout == "table":
        y = draw_front(margin, top, col_w, "left")
        y = draw_back(margin, y + 10, col_w, as_table=True)
    elif layout == "centered":
        y = draw_front(margin, top, col_w, "center")
        ImageDraw.Draw(img).line((margin, y, margin + col_w, y), fill=fg, width=2)
        y = draw_back(margin, y + 16, col_w)
    else:
        y = draw_front(margin, top, col_w, "left")
        if rng.random() < 0.6:
            ImageDraw.Draw(img).line((margin, y, margin + col_w, y), fill=fg, width=1)
        y = draw_back(margin, y + 12, col_w)
    y = p.draw_line(watermark, margin if layout != "two_panel" else 40, y + 24, col_w, fg) + 36
    H = int(min(H, max(y + rng.randint(20, 120), 420)))
    img = img.crop((0, 0, W, H))
    occupied.extend(w.box for ln in p.lines for w in ln.words)
    _decorate(img, rng, accent, bg, occupied)
    # drop words that the decorations overlapped (never happens with the chosen corners, kept as a guard)
    meta = {"layout": layout, "font_family": family, "display_font_family": display_family,
            "heldout_font": family in HELDOUT_FAMILIES or display_family in HELDOUT_FAMILIES,
            "base_font_px": base, "color_style": style}
    return img, p.lines, meta


# ============================================================================ scene + degradations
def _scene(rng: random.Random, w: int, h: int) -> np.ndarray:
    kind = rng.choice(["solid", "gradient", "noise", "wood", "fabric"])
    base = np.array(rng.choice([(120, 110, 100), (60, 60, 65), (200, 195, 185), (150, 120, 90), (90, 110, 130),
                                (30, 30, 30), (225, 225, 230), (170, 60, 50)]), np.float32)
    if kind == "solid":
        s = np.ones((h, w, 3), np.float32) * base
    elif kind == "gradient":
        t = np.linspace(0, 1, w)[None, :, None] if rng.random() < 0.5 else np.linspace(0, 1, h)[:, None, None]
        s = base * (0.6 + 0.6 * t) * np.ones((h, w, 3), np.float32)
    elif kind == "noise":
        n = cv2.resize(np.random.RandomState(rng.randint(0, 2**31 - 1)).rand(max(2, h // 40), max(2, w // 40)).astype(np.float32), (w, h))
        s = base * (0.7 + 0.6 * n[..., None])
    elif kind == "wood":
        yy = np.arange(h)[:, None]
        xx = np.arange(w)[None, :]
        rings = np.sin((yy * 0.05 + np.sin(xx * 0.01) * 6) * rng.uniform(0.6, 1.4))
        s = base * (0.85 + 0.15 * rings[..., None]) * np.ones((1, 1, 3))
    else:
        yy, xx = np.mgrid[0:h, 0:w]
        weave = (np.sin(xx * 0.9) * np.sin(yy * 0.9))
        s = base * (0.9 + 0.1 * weave[..., None])
    return np.clip(s, 0, 255).astype(np.uint8)


def _choose_conditions(rng: random.Random) -> dict:
    c = {}
    r = rng.random()
    if r < 0.42:
        c["rotation"] = 0.0
    elif r < 0.72:
        c["rotation"] = rng.uniform(1, 5) * rng.choice([-1, 1])
    elif r < 0.88:
        c["rotation"] = rng.uniform(5, 15) * rng.choice([-1, 1])
    elif r < 0.96:
        c["rotation"] = rng.uniform(15, 30) * rng.choice([-1, 1])
    else:
        c["rotation"] = float(rng.choice([90, 180, 270]))
    if rng.random() < 0.25:
        c["perspective"] = rng.uniform(0.03, 0.10)
    if rng.random() < 0.12:
        c["partial"] = {"side": rng.choice(["left", "right", "top", "bottom"]), "frac": rng.uniform(0.08, 0.25)}
    if rng.random() < 0.22:
        c["blur_rel"] = rng.uniform(0.05, 0.13)      # Gaussian sigma relative to the xs text size
    if rng.random() < 0.08:
        c["motion_rel"] = rng.uniform(0.25, 0.5)     # motion-blur length relative to the xs text size
    if rng.random() < 0.30:
        c["lighting"] = rng.choice(["gradient", "shadow", "glare", "dark", "bright"])
    if rng.random() < 0.14:
        c["low_contrast"] = rng.uniform(0.35, 0.6)
    if rng.random() < 0.25:
        c["noise"] = rng.uniform(4, 14)
    c["jpeg_quality"] = rng.randint(55, 93)
    # capture resolution is chosen through the size of the SMALLEST (xs) text in the output image:
    # 88 % readable photos (xs font 11-20 px), 12 % low-resolution photos (xs font 7-10 px)
    c["xs_font_px"] = rng.uniform(11, 20) if rng.random() < 0.88 else rng.uniform(7, 10)
    return c


def _apply_lighting(img: np.ndarray, kind: str, rng: random.Random) -> np.ndarray:
    h, w = img.shape[:2]
    f = img.astype(np.float32)
    if kind == "gradient":
        ang = rng.uniform(0, 2 * math.pi)
        yy, xx = np.mgrid[0:h, 0:w]
        t = (np.cos(ang) * xx / w + np.sin(ang) * yy / h)
        t = (t - t.min()) / (np.ptp(t) + 1e-6)
        f *= (0.45 + 0.75 * t)[..., None]
    elif kind == "shadow":
        mask = np.zeros((h, w), np.uint8)
        pts = np.array([[rng.randint(0, w), 0], [rng.randint(0, w), h], [w if rng.random() < 0.5 else 0, h],
                        [w if rng.random() < 0.5 else 0, 0]], np.int32)
        cv2.fillPoly(mask, [pts], 255)
        mask = cv2.GaussianBlur(mask, (0, 0), 25).astype(np.float32) / 255
        f *= (1 - 0.5 * mask)[..., None]
    elif kind == "glare":
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        yy, xx = np.mgrid[0:h, 0:w]
        rad = rng.uniform(0.08, 0.2) * max(w, h)
        g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad ** 2)))
        f = f + rng.uniform(80, 140) * g[..., None]
    elif kind == "dark":
        f *= rng.uniform(0.3, 0.5)
    elif kind == "bright":
        f = f * 0.6 + 110
    return np.clip(f, 0, 255).astype(np.uint8)


def compose_and_degrade(label: Image.Image, lines: list[PlacedLine], rng: random.Random,
                        base_px: int = 24) -> tuple[np.ndarray, list[dict], dict]:
    cond = _choose_conditions(rng)
    lab = cv2.cvtColor(np.array(label), cv2.COLOR_RGB2BGR)
    lh, lw = lab.shape[:2]
    mx, my = int(lw * rng.uniform(0.06, 0.2)), int(lh * rng.uniform(0.06, 0.2))
    SW, SH = lw + 2 * mx, lh + 2 * my
    scene = _scene(rng, SW, SH)
    # soft drop shadow under the label
    sh = np.zeros((SH, SW), np.float32)
    sh[my + 6:my + lh + 6, mx + 6:mx + lw + 6] = 1
    sh = cv2.GaussianBlur(sh, (0, 0), 6)
    scene = (scene.astype(np.float32) * (1 - 0.35 * sh[..., None])).astype(np.uint8)
    scene[my:my + lh, mx:mx + lw] = lab

    # ---- homography: rotation about centre + perspective jitter; output canvas fits all corners
    ang = cond["rotation"]
    cx, cy = SW / 2, SH / 2
    R = cv2.getRotationMatrix2D((cx, cy), -ang, 1.0)          # negative: clockwise-positive convention
    Hm = np.vstack([R, [0, 0, 1]])
    if "perspective" in cond:
        j = cond["perspective"]
        src = np.float32([[0, 0], [SW, 0], [SW, SH], [0, SH]])
        dst = src + np.float32([[rng.uniform(-j, j) * SW, rng.uniform(-j, j) * SH] for _ in range(4)])
        P = cv2.getPerspectiveTransform(src, dst)
        Hm = Hm @ P
    corners = cv2.perspectiveTransform(np.float32([[[0, 0], [SW, 0], [SW, SH], [0, SH]]]), Hm)[0]
    x0, y0 = corners.min(axis=0)
    x1, y1 = corners.max(axis=0)
    T = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    Hm = T @ Hm
    OW, OH = int(math.ceil(x1 - x0)), int(math.ceil(y1 - y0))
    fill = tuple(int(v) for v in scene[2, 2])
    out = cv2.warpPerspective(scene, Hm, (OW, OH), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=fill)

    def tf(pts):
        return cv2.perspectiveTransform(np.float32([pts]), Hm)[0]

    # ---- partial visibility: crop into the label from one side
    crop = (0, 0, OW, OH)
    if "partial" in cond:
        lab_quad = tf([[mx, my], [mx + lw, my], [mx + lw, my + lh], [mx, my + lh]])
        lx0, ly0 = lab_quad.min(axis=0)
        lx1, ly1 = lab_quad.max(axis=0)
        fr, side = cond["partial"]["frac"], cond["partial"]["side"]
        if side == "left":
            crop = (int(lx0 + fr * (lx1 - lx0)), 0, OW, OH)
        elif side == "right":
            crop = (0, 0, int(lx1 - fr * (lx1 - lx0)), OH)
        elif side == "top":
            crop = (0, int(ly0 + fr * (ly1 - ly0)), OW, OH)
        else:
            crop = (0, 0, OW, int(ly1 - fr * (ly1 - ly0)))
        out = out[crop[1]:crop[3], crop[0]:crop[2]]

    # ---- photometric
    if "lighting" in cond:
        out = _apply_lighting(out, cond["lighting"], rng)
    if "low_contrast" in cond:
        k = cond["low_contrast"]
        mean = out.reshape(-1, 3).mean(axis=0)
        out = np.clip(mean + (out.astype(np.float32) - mean) * k, 0, 255).astype(np.uint8)

    # ---- resize to capture resolution
    h, w = out.shape[:2]
    s = cond["xs_font_px"] / (base_px * SIZE_MULT["xs"])
    s = min(s, 2400 / max(h, w))                      # keep files reasonable
    cond["target_long_side"] = int(max(h, w) * s)
    out = cv2.resize(out, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    if "blur_rel" in cond:
        cond["blur"] = round(cond["blur_rel"] * cond["xs_font_px"], 2)
        out = cv2.GaussianBlur(out, (0, 0), cond["blur"])
    if "motion_rel" in cond:
        k = max(3, int(round(cond["motion_rel"] * cond["xs_font_px"])) | 1)
        cond["motion_blur"] = k
        ker = np.zeros((k, k), np.float32)
        ker[k // 2, :] = 1.0 / k
        M = cv2.getRotationMatrix2D((k / 2 - 0.5, k / 2 - 0.5), rng.uniform(0, 180), 1)
        ker = cv2.warpAffine(ker, M, (k, k))
        ker /= max(ker.sum(), 1e-6)
        out = cv2.filter2D(out, -1, ker)
    if "noise" in cond:
        nrs = np.random.RandomState(rng.randint(0, 2**31 - 1))
        out = np.clip(out.astype(np.float32) + nrs.normal(0, cond["noise"], out.shape), 0, 255).astype(np.uint8)
    FH, FW = out.shape[:2]
    gray_final = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)

    # ---- transform annotations
    ann_lines = []
    for li, pl in enumerate(lines):
        words = []
        for wd in pl.words:
            bx0, by0, bx1, by1 = wd.box
            q = np.float32([[bx0 + mx, by0 + my], [bx1 + mx, by0 + my], [bx1 + mx, by1 + my], [bx0 + mx, by1 + my]])
            q = tf(q)
            q[:, 0] -= crop[0]
            q[:, 1] -= crop[1]
            q *= s
            vis = _visible_fraction(q, FW, FH)
            contrast = _box_contrast(gray_final, q)
            words.append({"text": wd.text, "quad": q.round(1).tolist(), "visible_fraction": round(vis, 3),
                          "contrast": round(contrast, 1), "legible": bool(contrast >= LEGIBLE_CONTRAST)})
        vis_words = [w for w in words if w["visible_fraction"] >= VISIBLE_THRESHOLD]
        if not words:
            continue
        all_q = np.array([w["quad"] for w in (vis_words or words)]).reshape(-1, 2)
        line_quad = _min_quad([np.array(w["quad"]) for w in (vis_words or words)])
        ann_lines.append({
            "id": li,
            "text": " ".join(w["text"] for w in vis_words),
            "full_text": pl.text,
            "fields": pl.fields, "field": pl.fields[0] if pl.fields else "other",
            "size": pl.size, "lang": pl.lang, "dotmatrix": pl.dotmatrix, "kv_part": pl.kv_part, "wrapped": pl.wrapped,
            "legible": bool(vis_words) and sum(w["legible"] for w in vis_words) >= 0.5 * len(vis_words),
            "visible": bool(vis_words), "partial": len(vis_words) < len(words) and any(w["visible_fraction"] > 0 for w in words),
            "quad": line_quad.round(1).tolist(),
            "bbox": [round(float(all_q[:, 0].min()), 1), round(float(all_q[:, 1].min()), 1),
                     round(float(all_q[:, 0].max()), 1), round(float(all_q[:, 1].max()), 1)],
            "words": words,
        })
    cond["scale"] = round(s, 4)
    cond["crop"] = list(map(int, crop))
    return out, ann_lines, cond


def _box_contrast(gray: np.ndarray, q: np.ndarray) -> float:
    """Intensity spread (std-dev) inside the word box of the FINAL image: ~0 means the word was washed out
    by glare / darkness / contrast reduction and is not legible even to a person."""
    x0, y0 = np.floor(q.min(axis=0)).astype(int)
    x1, y1 = np.ceil(q.max(axis=0)).astype(int)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(gray.shape[1], x1), min(gray.shape[0], y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return 0.0
    return float(gray[y0:y1, x0:x1].std())


def _visible_fraction(q: np.ndarray, W: int, H: int) -> float:
    from shapely.geometry import Polygon, box
    try:
        poly = Polygon(q)
        if not poly.is_valid or poly.area <= 0:
            return 0.0
        return float(poly.intersection(box(0, 0, W, H)).area / poly.area)
    except Exception:
        return 0.0


def _min_quad(quads: list[np.ndarray]) -> np.ndarray:
    """Line quad = first word's left edge + last word's right edge (follows rotation / perspective)."""
    first, last = quads[0], quads[-1]
    return np.float32([first[0], last[1], last[2], first[3]])


def condition_tags(meta: dict, cond: dict) -> list[str]:
    t = []
    rot = cond.get("rotation", 0)
    if rot in (90.0, 180.0, 270.0):
        t.append("rotated_90")
    elif abs(rot) >= 5:
        t.append("rotated")
    elif abs(rot) > 0:
        t.append("slight_rotation")
    if "perspective" in cond:
        t.append("perspective")
    if "partial" in cond:
        t.append("partial_visibility")
    if "blur_rel" in cond or "motion_rel" in cond:
        t.append("blurry")
    if "lighting" in cond:
        t.append(f"lighting_{cond['lighting']}")
    if "low_contrast" in cond or meta.get("color_style") == "low_contrast":
        t.append("low_contrast")
    if meta.get("color_style") == "dark":
        t.append("light_on_dark")
    if "noise" in cond:
        t.append("noisy")
    if cond.get("xs_font_px", 20) < 10.5:
        t.append("low_resolution")
    if meta.get("layout") == "table":
        t.append("table_layout")
    if meta.get("heldout_font"):
        t.append("unseen_font")
    if not t or t == ["slight_rotation"]:
        t.append("clear")
    return t


def encode_jpeg(bgr: np.ndarray, quality: int, comment: str) -> bytes:
    """JPEG with the synthetic notice in both the COM segment and EXIF ImageDescription."""
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    exif = Image.Exif()
    exif[0x010E] = comment          # ImageDescription
    exif[0x0131] = "SafeMetric synthetic label generator"   # Software
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, exif=exif.tobytes(), comment=comment.encode("utf-8"))
    return buf.getvalue()
