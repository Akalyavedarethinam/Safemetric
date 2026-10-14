"""
Render a clear, FICTIONAL demo product - a 500 g malt health-drink carton - as front / back / side product photos
(white studio background), plus an overview image with all three views.

    python scripts/make_demo_malt_drink.py      # -> samples/malt_drink_500g/{front,back,left}.jpg + samples/malt_drink_500g_overview.jpg

"MALTIVA" and "Sunrise Nutrition Foods" are invented. The FSSAI number, phone number, barcode and e-mail domain
(*.example.in) are made up. Every panel carries "SYNTHETIC SAMPLE - NOT A REAL PRODUCT". Nothing here describes a
real product, and the images must not be presented as evidence about any real product.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "training" / "fonts"
OUT = ROOT / "samples" / "malt_drink_500g"

BROWN = (96, 48, 22)
DARK = (58, 30, 14)
CREAM = (255, 251, 243)
GOLD = (236, 172, 42)
GREEN = (22, 128, 60)
INK = (30, 24, 20)
PW, PH = 760, 1320           # front / back panel
SW = 460                     # side panel width

BOLD, REG, BRAND, MONO = "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Poppins-Bold.ttf", "DejaVuSansMono.ttf"
COND_B, COND = "DejaVuSansCondensed-Bold.ttf", "DejaVuSansCondensed.ttf"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def ctext(d, cx, y, text, f, fill=INK):
    d.text((cx - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


def veg_mark(d, x, y, s=40):
    d.rectangle([x, y, x + s, y + s], outline=GREEN, width=4)
    d.ellipse([x + 10, y + 10, x + s - 10, y + s - 10], fill=GREEN)


def swirl(d, w, y0):
    """Chocolate-milk wave at the bottom of the panel (decoration)."""
    pts = [(x, y0 + 26 * np.sin(x / 70.0)) for x in range(0, w + 10, 10)]
    d.polygon(pts + [(w, PH), (0, PH)], fill=BROWN)
    pts2 = [(x, y0 + 40 + 20 * np.sin(x / 55.0 + 1.3)) for x in range(0, w + 10, 10)]
    d.polygon(pts2 + [(w, PH), (0, PH)], fill=DARK)


def notice(d, w, fill=(150, 140, 130)):
    ctext(d, w / 2, PH - 34, "SYNTHETIC SAMPLE - NOT A REAL PRODUCT", font(REG, 16), fill)


# ------------------------------------------------------------------ panels
def front_panel():
    im = Image.new("RGB", (PW, PH), GOLD)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 40, PW - 34, 1090], 36, fill=CREAM)
    d.rounded_rectangle([90, 80, PW - 90, 330], 28, outline=BROWN, width=5)
    ctext(d, PW / 2, 100, "MALTIVA", font(BRAND, 128), BROWN)
    ctext(d, PW / 2, 262, "CHOCOLATE", font(BOLD, 38), (170, 90, 30))
    ctext(d, PW / 2, 372, "MALT BASED HEALTH", font(BOLD, 50), DARK)
    ctext(d, PW / 2, 434, "DRINK POWDER", font(BOLD, 50), DARK)
    veg_mark(d, 70, 520)
    # illustration: a mug of malt drink
    d.rounded_rectangle([250, 560, 510, 820], 30, fill=(255, 255, 255), outline=(210, 200, 190), width=3)
    d.ellipse([268, 572, 492, 632], fill=(128, 68, 34))
    d.arc([440, 630, 580, 760], -80, 80, fill=(210, 200, 190), width=24)
    ctext(d, PW / 2, 870, "With Vitamins & Minerals", font(REG, 34), DARK)
    ctext(d, PW / 2, 920, "for Strength & Stamina", font(REG, 34), DARK)
    d.rounded_rectangle([110, 1120, PW - 110, 1230], 26, fill=CREAM)
    ctext(d, PW / 2, 1142, "Net Wt. 500 g", font(BOLD, 54), DARK)
    notice(d, PW, (120, 80, 30))
    return im


def back_panel():
    im = Image.new("RGB", (PW, PH), GOLD)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, PW - 30, PH - 60], 26, fill=(245, 243, 238))
    x0, y = 64, 60
    tb, tr = font(COND_B, 34), font(COND, 31)
    # nutrition table
    d.rectangle([x0, y, PW - 64, y + 380], outline=INK, width=3)
    ctext(d, PW / 2, y + 12, "Nutritional Information", font(COND_B, 34), DARK)
    ctext(d, PW / 2, y + 54, "(Approx. values per 100 g)", font(COND_B, 30), DARK)
    rows = [("Energy", "385 kcal"), ("Protein", "7.0 g"), ("Carbohydrate", "83.0 g"), ("Total Fat", "2.5 g"),
            ("Calcium", "480 mg")]
    ty = y + 100
    for k, v in rows:
        d.line([x0, ty, PW - 64, ty], fill=INK, width=2)
        d.text((x0 + 20, ty + 8), k, font=tr, fill=INK)
        d.text((PW - 84 - d.textlength(v, font=tr), ty + 8), v, font=tr, fill=INK)
        ty += 56
    d.line([470, y + 100, 470, y + 380], fill=INK, width=2)
    y += 410
    d.text((x0, y), "Ingredients:", font=tb, fill=DARK); y += 44
    for t in ["Malted Barley (32%), Sugar, Wheat", "Flour, Milk Solids, Cocoa Powder (8%),", "Minerals, Vitamins, Salt."]:
        d.text((x0, y), t, font=tr, fill=INK); y += 40
    y += 18
    d.text((x0, y), "Manufactured & Packed by:", font=tb, fill=DARK); y += 44
    for t in ["Sunrise Nutrition Foods Pvt. Ltd.,", "Plot 14, Phase II, IDA Jeedimetla,",
              "Hyderabad, Telangana - 500055, India."]:
        d.text((x0, y), t, font=tr, fill=INK); y += 40
    y += 14
    d.text((x0, y), "FSSAI Lic. No. 13626999000417", font=tb, fill=INK); y += 48
    d.text((x0, y), "Country of Origin: India", font=tr, fill=INK); y += 56
    d.rounded_rectangle([x0, y, PW - 64, y + 200], 16, outline=DARK, width=3)
    yy = y + 14
    for t, f in (("For consumer complaints contact:", tb), ("Customer Care Manager", tr),
                 ("Phone: 1800 102 7788 (Toll Free)", tr), ("Email: care@maltiva.example.in", tr)):
        d.text((x0 + 20, yy), t, font=f, fill=INK); yy += 44
    y += 222
    # a fictional barcode (decoration only)
    rng = np.random.default_rng(7)
    bx = x0
    while bx < x0 + 300:
        w = int(rng.integers(2, 6))
        d.rectangle([bx, y, bx + w, y + 70], fill=INK)
        bx += w + int(rng.integers(2, 6))
    notice(d, PW)
    return im


def side_panel():
    im = Image.new("RGB", (SW, PH), GOLD)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([22, 30, SW - 22, PH - 60], 22, fill=(245, 243, 238))
    ctext(d, SW / 2, 60, "MALTIVA", font(BRAND, 64), BROWN)
    y = 180
    d.rounded_rectangle([44, y, SW - 44, y + 250], 16, outline=DARK, width=4)
    d.text((60, y + 24), "M.R.P. ₹285.00", font=font(BOLD, 34), fill=INK)
    d.text((66, y + 86), "(Incl. of all taxes)", font=font(REG, 30), fill=INK)
    d.text((66, y + 140), "Unit Sale Price:", font=font(REG, 30), fill=INK)
    d.text((66, y + 184), "₹57.00 per 100 g", font=font(BOLD, 32), fill=INK)
    y += 290
    # the ink-jet block printed on the carton at packing time
    d.rectangle([44, y, SW - 44, y + 210], fill=(244, 244, 244), outline=(160, 160, 160), width=2)
    m = font(MONO, 30)
    for i, t in enumerate(("PKD: 08/2026", "USE BY: 07/2027", "BATCH NO: MV2608A")):
        d.text((66, y + 22 + 62 * i), t, font=m, fill=INK)
    y += 250
    r = font(REG, 29)
    for t in ["Best Before 12 months", "from packing.", "", "Store in a cool, dry", "place. Close tightly",
              "after use.", "", "Add 2 heaped teaspoons", "to a cup of warm milk."]:
        d.text((52, y), t, font=r, fill=INK); y += 40
    veg_mark(d, 52, y + 18)
    notice(d, SW)
    return im


# ------------------------------------------------------------------ carton photo
def carton_photo(panel: Image.Image, seed: int, lit_left=True) -> Image.Image:
    """Put the printed panel on a carton with a cap and top flap, soft side shading and a floor shadow,
    on a white studio background - like a product photo."""
    w, h = panel.size
    top = 150
    BW, BH = w + 240, h + top + 190
    img = Image.new("RGB", (BW, BH), (255, 255, 255))
    d = ImageDraw.Draw(img)
    ox, oy = 120, top + 40
    # floor shadow
    sh = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(sh).ellipse([ox - 20, oy + h - 30, ox + w + 20, oy + h + 60], fill=120)
    sh = sh.filter(ImageFilter.GaussianBlur(26))
    img.paste((150, 150, 150), (0, 0), sh)
    # top flap (gable) and cap
    d.polygon([(ox, oy), (ox + 18, oy - 70), (ox + w - 18, oy - 70), (ox + w, oy)], fill=(214, 152, 32))
    d.polygon([(ox + 18, oy - 70), (ox + w - 18, oy - 70), (ox + w - 24, oy - 86), (ox + 24, oy - 86)],
              fill=(196, 138, 26))
    cx = ox + w // 2
    d.rounded_rectangle([cx - 70, oy - 150, cx + 70, oy - 66], 14, fill=(250, 250, 250), outline=(205, 205, 205), width=3)
    for i in range(9):
        x = cx - 60 + i * 15
        d.line([x, oy - 146, x, oy - 72], fill=(226, 226, 226), width=3)
    img.paste(panel, (ox, oy))
    # 3-D shading: darker towards the edges, a highlight stripe on the lit side
    arr = np.asarray(img).astype(np.float32)
    xs = (np.arange(w) / (w - 1)) * 2 - 1
    shade = 1.0 - 0.10 * np.abs(xs) ** 3 - (0.05 * (xs if lit_left else -xs)).clip(0, None)
    hl = 0.015 * np.exp(-((xs - (-0.55 if lit_left else 0.55)) ** 2) / 0.02)
    region = arr[oy:oy + h, ox:ox + w]
    region[:] = region * shade[None, :, None] + 255 * hl[None, :, None]
    rng = np.random.default_rng(seed)
    arr += rng.normal(0, 1.6, arr.shape)                  # a little sensor noise
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def overview(photos: list[Image.Image]) -> Image.Image:
    H = max(p.height for p in photos) + 110
    W = sum(p.width for p in photos) + 60
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    x = 30
    for p, name in zip(photos, ("Front View", "Back View", "Side View")):
        im.paste(p, (x, 0))
        ctext(d, x + p.width / 2, H - 90, name, font(REG, 46), INK)
        x += p.width
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    photos = []
    for name, fn, seed, lit in (("front", front_panel, 1, True), ("back", back_panel, 2, True),
                                ("left", side_panel, 3, False)):
        p = carton_photo(fn(), seed, lit)
        exif = Image.Exif()
        exif[0x010E] = "SYNTHETIC SAMPLE - NOT A REAL PRODUCT (SafeMetric demo)"
        p.save(OUT / f"{name}.jpg", "JPEG", quality=92, exif=exif)
        photos.append(p)
        print("wrote", OUT / f"{name}.jpg")
    ov = overview(photos)
    ov.save(OUT.parent / "malt_drink_500g_overview.jpg", "JPEG", quality=88)
    print("wrote", OUT.parent / "malt_drink_500g_overview.jpg")


if __name__ == "__main__":
    main()
