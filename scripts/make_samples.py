"""
Generate synthetic packaged-commodity label photographs (multiple package sides) for
testing and demonstration.  Output: samples/<product>/<side>.jpg

These are *test fixtures only* - the application never uses them to produce results;
it analyses whatever images the inspector uploads.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "samples"
random.seed(7)


def font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"])
    for base in ("/usr/share/fonts/truetype/dejavu/", "C:/Windows/Fonts/", "/Library/Fonts/", ""):
        for n in names:
            try:
                return ImageFont.truetype(base + n, size)
            except OSError:
                continue
    return ImageFont.load_default()


def panel(lines, size=(1300, 1700), bg=(252, 250, 240), accent=(25, 70, 150), header=True, photo=True, rotate=0.0):
    img = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(img)
    if header:
        d.rectangle([0, 0, size[0], 120], fill=accent)
        d.rectangle([0, size[1] - 70, size[0], size[1]], fill=accent)
    y = 170
    for item in lines:
        text, sz, bold, color = (item + (False, (20, 20, 20)))[:4] if len(item) < 4 else item
        if text == "---":
            d.line([60, y + 8, size[0] - 60, y + 8], fill=(170, 170, 170), width=3)
            y += 32
            continue
        d.text((70, y), text, font=font(sz, bold), fill=color)
        y += int(sz * 1.42)
    if photo:
        # simulate a photograph: place on a table-coloured background, slight rotation, blur and noise
        canvas = Image.new("RGB", (size[0] + 160, size[1] + 160), (120, 110, 100))
        canvas.paste(img, (80, 80))
        img = canvas.rotate(rotate, resample=Image.BICUBIC, expand=False, fillcolor=(120, 110, 100))
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        px = img.load()
        for _ in range(9000):
            x, yy = random.randrange(img.width), random.randrange(img.height)
            r, g, b = px[x, yy]
            n = random.randint(-25, 25)
            px[x, yy] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return img


K, G = (20, 20, 20), (95, 95, 95)
BLUE, BROWN, GREEN, PURPLE, GREY = (25, 70, 150), (150, 60, 10), (40, 110, 40), (110, 40, 130), (60, 60, 70)

PRODUCTS = {
    # 1. well-labelled food product (should PASS most checks; physical checks still need verification)
    "basmati_rice_1kg": {
        "front": dict(lines=[("ROYAL HARVEST", 104, True, BLUE), ("Premium Basmati Rice", 66, True, K), ("---",),
                             ("Net Quantity: 1 kg", 96, True, K), ("MRP ₹185.00", 70, True, K),
                             ("(Inclusive of all taxes)", 40, False, K)], accent=BLUE),
        "back": dict(lines=[("Unit Sale Price: ₹185.00 per kg", 40, False, K),
                            ("Month & Year of Packing: 08/2026", 40, False, K),
                            ("Best Before: 12 months from packing", 38, False, K), ("---",),
                            ("Manufactured & Packed by:", 38, True, K),
                            ("Royal Harvest Foods Pvt. Ltd.,", 38, False, K),
                            ("Plot 21, MIDC Industrial Area, Nagpur,", 38, False, K),
                            ("Maharashtra - 440016, India", 38, False, K),
                            ("FSSAI Lic. No. 11521999000123", 36, False, K),
                            ("Country of Origin: India", 38, False, K),
                            ("Ingredients: Basmati Rice", 36, False, K), ("---",),
                            ("For consumer complaints contact:", 38, True, K),
                            ("Customer Care Manager, Royal Harvest Foods", 34, False, K),
                            ("Phone: 1800 123 4567", 38, False, K),
                            ("Email: care@royalharvest.in", 38, False, K),
                            ("Batch No: RH2608B", 34, False, K)], accent=BLUE, rotate=2.5),
    },
    # 2. deliberately defective food product
    "wheat_atta_defective": {
        "front": dict(lines=[("GOLDEN MILL", 104, True, BROWN), ("Whole Wheat Atta", 66, True, K), ("---",),
                             ("Net Wt. approx 500 gms", 72, True, K), ("MRP Rs. 42", 64, True, K)], accent=BROWN),
        "back": dict(lines=[("Packed by:", 40, True, K), ("Golden Mill Industries", 40, False, K),
                            ("Best before 6 months", 36, False, G),
                            ("MRP Rs. 45 plus local taxes", 38, False, G)], accent=BROWN, rotate=-1.5),
    },
    # 3. imported product with a wrong unit sale price
    "olive_oil_imported": {
        "front": dict(lines=[("OLIVA DORO", 104, True, GREEN), ("Extra Virgin Olive Oil", 62, True, K), ("---",),
                             ("Net Volume: 500 ml", 84, True, K), ("MRP ₹899.00", 66, True, K),
                             ("Inclusive of all taxes", 40, False, K)], accent=GREEN),
        "back": dict(lines=[("Unit Sale Price: ₹2.50 per ml", 40, False, K), ("Mfg Date: MAR 2026", 40, False, K),
                            ("Best Before: MAR 2028", 38, False, K), ("Imported by:", 38, True, K),
                            ("Oliva Trading India LLP, 14 Park Street,", 36, False, K),
                            ("Kolkata, West Bengal - 700016", 36, False, K),
                            ("Country of Origin: Spain", 40, False, K),
                            ("Consumer Care: +91 33 4000 1234", 38, False, K),
                            ("care@olivadoro.in", 36, False, K),
                            ("FSSAI Lic. No. 10019022009876", 34, False, K)], accent=GREEN),
    },
    # 4. cosmetic
    "herbal_shampoo_cosmetic": {
        "front": dict(lines=[("SILKEN", 110, True, PURPLE), ("Herbal Shampoo", 70, True, K), ("---",),
                             ("Net Vol. 180 ml", 80, True, K), ("M.R.P. ₹ 210.00", 60, True, K),
                             ("Incl. of all taxes", 38, False, K)], accent=PURPLE),
        "back": dict(lines=[("Ingredients: Aqua, Sodium Laureth Sulfate,", 32, False, K),
                            ("Glycerin, Aloe Vera Extract, Fragrance", 32, False, K),
                            ("Batch No: SH24A19", 38, False, K), ("Mfg. Date: 05/2026", 38, False, K),
                            ("Use before: 04/2029", 38, False, K),
                            ("Manufactured by:", 38, True, K), ("Silken Personal Care Ltd.,", 36, False, K),
                            ("45 Industrial Estate, Baddi,", 36, False, K),
                            ("Himachal Pradesh 173205", 36, False, K),
                            ("Customer Care: 1800 200 3344", 38, False, K),
                            ("Email: hello@silken.co.in", 36, False, K),
                            ("Unit Sale Price: ₹116.67 per 100 ml", 34, False, K)], accent=PURPLE),
    },
    # 5. electronics (sold by number)
    "usb_charger_electronics": {
        "front": dict(lines=[("VOLTEX", 110, True, GREY), ("USB Fast Charger 20W", 64, True, K), ("---",),
                             ("Net Quantity: 1 N", 80, True, K), ("MRP ₹ 799.00", 64, True, K),
                             ("(Incl. of all taxes)", 38, False, K)], accent=GREY),
        "back": dict(lines=[("Month & Year of Manufacture: 04/2026", 38, False, K),
                            ("Manufactured by:", 38, True, K), ("Voltex Electronics Pvt Ltd,", 36, False, K),
                            ("B-12, Sector 63, Noida,", 36, False, K), ("Uttar Pradesh - 201301", 36, False, K),
                            ("R-41012345  IS 13252", 36, False, K), ("Country of Origin: India", 38, False, K),
                            ("Consumer Care: 1800 419 8800", 38, False, K),
                            ("support@voltex.in", 36, False, K)], accent=GREY),
    },
}


def main():
    for product, sides in PRODUCTS.items():
        d = OUT / product
        d.mkdir(parents=True, exist_ok=True)
        for side, spec in sides.items():
            lines = [tuple(l) if len(l) == 4 else (l[0], 0, False, K) for l in spec["lines"]]
            img = panel(lines, accent=spec.get("accent", BLUE), rotate=spec.get("rotate", 0.0))
            img.save(d / f"{side}.jpg", quality=90)
            print("wrote", d / f"{side}.jpg")


if __name__ == "__main__":
    main()
