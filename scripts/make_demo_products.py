"""
Render FICTIONAL demo products as product photos (front / back / left side + an overview) for SafeMetric demos.

    python scripts/make_demo_products.py        # -> samples/<product>/{front,back,left}.jpg + samples/<product>_overview.jpg

Brands, companies, addresses, FSSAI numbers, phone numbers and e-mail domains (*.example.in) are all invented.
Every panel carries "SYNTHETIC SAMPLE - NOT A REAL PRODUCT". One product (cookies_200g_defective) is deliberately
labelled WRONGLY to demonstrate the potential findings the rule engine raises.
The MALTIVA malt drink is made by scripts/make_demo_malt_drink.py.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "training" / "fonts"
SAMPLES = ROOT / "samples"
INK = (30, 24, 20)
LABEL = (245, 243, 238)
GREEN = (22, 128, 60)
PW, PH, SW = 760, 1320, 460
BOLD, REG, BRAND, MONO = "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Poppins-Bold.ttf", "DejaVuSansMono.ttf"
COND_B, COND = "DejaVuSansCondensed-Bold.ttf", "DejaVuSansCondensed.ttf"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def ctext(d, cx, y, text, f, fill=INK):
    d.text((cx - d.textlength(text, font=f) / 2, y), text, font=f, fill=fill)


def fit(d, text, name, size, max_w):
    while size > 12 and d.textlength(text, font=font(name, size)) > max_w:
        size -= 1
    return font(name, size)


def veg_mark(d, x, y, s=40, veg=True):
    c = GREEN if veg else (160, 40, 30)
    d.rectangle([x, y, x + s, y + s], outline=c, width=4)
    d.ellipse([x + 10, y + 10, x + s - 10, y + s - 10], fill=c)


def notice(d, w):
    ctext(d, w / 2, PH - 34, "SYNTHETIC SAMPLE - NOT A REAL PRODUCT", font(REG, 16), (120, 110, 100))


# ------------------------------------------------------------------ illustrations (generic shapes only)
def illo(d, kind, cx, cy, p):
    rng = np.random.default_rng(3)
    if kind == "rice":
        d.chord([cx - 170, cy - 60, cx + 170, cy + 150], 0, 180, fill=p["dark"])
        d.ellipse([cx - 170, cy - 60, cx + 170, cy + 30], fill=(252, 250, 240), outline=p["dark"], width=4)
        for _ in range(90):
            x, y = cx + rng.uniform(-140, 140), cy - 15 + rng.uniform(-30, 25)
            a = rng.uniform(0, math.pi)
            dx, dy = 14 * math.cos(a), 5 * math.sin(a)
            d.line([x - dx, y - dy, x + dx, y + dy], fill=(215, 205, 180), width=5)
    elif kind == "oil":
        d.polygon([(cx, cy - 170), (cx - 110, cy + 20), (cx + 110, cy + 20)], fill=p["accent"])
        d.ellipse([cx - 115, cy - 60, cx + 115, cy + 150], fill=p["accent"])
        d.ellipse([cx - 60, cy - 10, cx - 20, cy + 60], fill=(255, 245, 190))
    elif kind == "cookies":
        for ox, oy in ((-90, 20), (80, -10), (0, 90)):
            d.ellipse([cx + ox - 90, cy + oy - 90, cx + ox + 90, cy + oy + 90], fill=(222, 170, 92), outline=(170, 110, 50), width=5)
            for a in range(0, 360, 60):
                r = 50
                x, y = cx + ox + r * math.cos(math.radians(a)), cy + oy + r * math.sin(math.radians(a))
                d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(150, 90, 40))
    elif kind == "leaves":
        for a, s in ((-35, 1.0), (15, 0.9), (60, 0.8)):
            L = 170 * s
            pts = []
            for t in np.linspace(0, math.pi, 30):
                pts.append((L * t / math.pi, 45 * s * math.sin(t)))
            pts += [(x, -y) for x, y in reversed(pts)]
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            d.polygon([(cx - 60 + x * ca - y * sa, cy + 60 - x * sa - y * ca) for x, y in pts], fill=p["accent"])
    elif kind == "bubbles":
        for _ in range(14):
            r = rng.uniform(18, 60)
            x, y = cx + rng.uniform(-170, 170), cy + rng.uniform(-110, 110)
            d.ellipse([x - r, y - r, x + r, y + r], outline=p["accent"], width=6)


# ------------------------------------------------------------------ panels
def front_panel(p):
    im = Image.new("RGB", (PW, PH), p["color"])
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([34, 40, PW - 34, 1090], 36, fill=LABEL)
    d.rounded_rectangle([80, 80, PW - 80, 330], 28, outline=p["dark"], width=5)
    ctext(d, PW / 2, 104, p["brand"], fit(d, p["brand"], BRAND, 118, PW - 200), p["dark"])
    ctext(d, PW / 2, 262, p["tag"], font(BOLD, 36), p["accent_text"])
    y = 372
    for line in p["name_lines"]:
        ctext(d, PW / 2, y, line, fit(d, line, BOLD, 50, PW - 140), p["dark"])
        y += 62
    if p.get("veg") is not None:
        veg_mark(d, 70, 520, veg=p["veg"])
    illo(d, p["illo"], PW / 2, 720, p)
    y = 900
    for line in p["claims"]:
        ctext(d, PW / 2, y, line, font(REG, 34), p["dark"])
        y += 48
    d.rounded_rectangle([100, 1120, PW - 100, 1230], 26, fill=LABEL)
    ctext(d, PW / 2, 1142, p["front_qty"], fit(d, p["front_qty"], BOLD, 54, PW - 240), p["dark"])
    notice(d, PW)
    return im


def back_panel(p):
    im = Image.new("RGB", (PW, PH), p["color"])
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, PW - 30, PH - 60], 26, fill=LABEL)
    x0, y = 64, 60
    tb, tr = font(COND_B, 34), font(COND, 31)
    if p.get("nutrition"):
        title, basis, rows = p["nutrition"]
        th = 100 + 56 * len(rows)
        d.rectangle([x0, y, PW - 64, y + th], outline=INK, width=3)
        ctext(d, PW / 2, y + 12, title, font(COND_B, 34), p["dark"])
        ctext(d, PW / 2, y + 54, basis, font(COND_B, 30), p["dark"])
        ty = y + 100
        for k, v in rows:
            d.line([x0, ty, PW - 64, ty], fill=INK, width=2)
            d.text((x0 + 20, ty + 8), k, font=tr, fill=INK)
            d.text((PW - 84 - d.textlength(v, font=tr), ty + 8), v, font=tr, fill=INK)
            ty += 56
        d.line([470, y + 100, 470, y + th], fill=INK, width=2)
        y += th + 30
    d.text((x0, y), p["ingredients_label"], font=tb, fill=p["dark"]); y += 44
    for t in p["ingredients"]:
        d.text((x0, y), t, font=tr, fill=INK); y += 40
    y += 18
    d.text((x0, y), p["mfr_label"], font=tb, fill=p["dark"]); y += 44
    for t in p["mfr"]:
        d.text((x0, y), t, font=tr, fill=INK); y += 40
    y += 14
    if p.get("fssai"):
        d.text((x0, y), f"FSSAI Lic. No. {p['fssai']}", font=tb, fill=INK); y += 48
    d.text((x0, y), "Country of Origin: India", font=tr, fill=INK); y += 56
    if p.get("care"):
        box = [("For consumer complaints contact:", tb)] + [(t, tr) for t in p["care"]]
        d.rounded_rectangle([x0, y, PW - 64, y + 20 + 44 * len(box)], 16, outline=p["dark"], width=3)
        yy = y + 14
        for t, f in box:
            d.text((x0 + 20, yy), t, font=f, fill=INK); yy += 44
        y += 40 + 44 * len(box)
    else:
        for t in p.get("back_extra", []):
            d.text((x0, y), t, font=tr, fill=INK); y += 40
        y += 20
    rng = np.random.default_rng(7)
    bx = x0
    while bx < x0 + 300 and y + 70 < PH - 70:
        w = int(rng.integers(2, 6))
        d.rectangle([bx, y, bx + w, y + 70], fill=INK)
        bx += w + int(rng.integers(2, 6))
    notice(d, PW)
    return im


def side_panel(p):
    im = Image.new("RGB", (SW, PH), p["color"])
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([22, 30, SW - 22, PH - 60], 22, fill=LABEL)
    ctext(d, SW / 2, 60, p["brand"], fit(d, p["brand"], BRAND, 64, SW - 80), p["dark"])
    y = 180
    box_h = 70 + 50 * len(p["price_lines"])
    d.rounded_rectangle([44, y, SW - 44, y + box_h], 16, outline=p["dark"], width=4)
    d.text((60, y + 22), p["mrp_line"], font=fit(d, p["mrp_line"], BOLD, 34, SW - 130), fill=INK)
    yy = y + 80
    for t, bold in p["price_lines"]:
        d.text((66, yy), t, font=fit(d, t, BOLD if bold else REG, 30, SW - 130), fill=INK); yy += 48
    y += box_h + 40
    stamp = p["stamp"]
    d.rectangle([44, y, SW - 44, y + 30 + 62 * len(stamp)], fill=(236, 236, 236), outline=(160, 160, 160), width=2)
    for i, t in enumerate(stamp):
        d.text((66, y + 22 + 62 * i), t, font=fit(d, t, MONO, 30, SW - 130), fill=INK)
    y += 70 + 62 * len(stamp)
    for t in p["side_text"]:
        d.text((52, y), t, font=font(REG, 29), fill=INK); y += 40
    notice(d, SW)
    return im


# ------------------------------------------------------------------ pack photo
def pack_photo(panel, p, seed, lit_left=True):
    w, h = panel.size
    shape = p["shape"]
    top = 170
    BW, BH = w + 240, h + top + 190
    img = Image.new("RGB", (BW, BH), (255, 255, 255))
    d = ImageDraw.Draw(img)
    ox, oy = 120, top + 40
    sh = Image.new("L", (BW, BH), 0)
    ImageDraw.Draw(sh).ellipse([ox - 20, oy + h - 30, ox + w + 20, oy + h + 60], fill=120)
    img.paste((150, 150, 150), (0, 0), sh.filter(ImageFilter.GaussianBlur(26)))
    col, dk = p["color"], tuple(int(c * 0.82) for c in p["color"])
    cx = ox + w // 2
    if shape == "carton":
        d.polygon([(ox, oy), (ox + 18, oy - 70), (ox + w - 18, oy - 70), (ox + w, oy)], fill=dk)
        d.rounded_rectangle([cx - 70, oy - 150, cx + 70, oy - 66], 14, fill=(250, 250, 250), outline=(205, 205, 205), width=3)
    elif shape == "pouch":
        d.rounded_rectangle([ox, oy - 90, ox + w, oy + 40], 30, fill=col)
        d.rectangle([ox + 10, oy - 80, ox + w - 10, oy - 50], fill=dk)
        for x in range(ox + 20, ox + w - 20, 18):
            d.line([x, oy - 80, x, oy - 50], fill=col, width=4)
        d.ellipse([cx - 22, oy - 40, cx + 22, oy + 4], fill=(255, 255, 255))
    elif shape == "bottle":
        nw = w // 3
        d.polygon([(ox, oy + 10), (cx - nw // 2, oy - 90), (cx + nw // 2, oy - 90), (ox + w, oy + 10)], fill=col)
        d.rectangle([cx - nw // 2, oy - 120, cx + nw // 2, oy - 88], fill=col)
        d.rounded_rectangle([cx - nw // 2 - 10, oy - 170, cx + nw // 2 + 10, oy - 116], 12, fill=p["cap"])
    img.paste(panel, (ox, oy))
    arr = np.asarray(img).astype(np.float32)
    xs = (np.arange(w) / (w - 1)) * 2 - 1
    shade = 1.0 - 0.10 * np.abs(xs) ** 3 - (0.05 * (xs if lit_left else -xs)).clip(0, None)
    hl = 0.015 * np.exp(-((xs - (-0.55 if lit_left else 0.55)) ** 2) / 0.02)
    region = arr[oy:oy + h, ox:ox + w]
    region[:] = region * shade[None, :, None] + 255 * hl[None, :, None]
    arr += np.random.default_rng(seed).normal(0, 1.6, arr.shape)
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def overview(photos):
    H = max(q.height for q in photos) + 110
    W = sum(q.width for q in photos) + 60
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    x = 30
    for q, name in zip(photos, ("Front View", "Back View", "Side View")):
        im.paste(q, (x, H - 110 - q.height))
        ctext(d, x + q.width / 2, H - 90, name, font(REG, 46), INK)
        x += q.width
    return im


# ------------------------------------------------------------------ product specifications
PRODUCTS = {
    "basmati_rice_5kg": dict(
        brand="ANNAVIA", tag="PREMIUM", name_lines=["EXTRA LONG GRAIN", "BASMATI RICE"], shape="pouch",
        color=(34, 110, 70), dark=(20, 70, 42), accent=(34, 110, 70), accent_text=(150, 110, 30), illo="rice", veg=True,
        claims=["Aged for 12 months", "Aromatic & Fluffy"], front_qty="Net Wt. 5 kg",
        nutrition=("Nutritional Information", "(Approx. values per 100 g)",
                   [("Energy", "350 kcal"), ("Protein", "7.5 g"), ("Carbohydrate", "78.0 g"), ("Total Fat", "0.6 g")]),
        ingredients_label="Ingredients:", ingredients=["Basmati Rice (100%)."],
        mfr_label="Packed & Marketed by:",
        mfr=["Annavia Agro Foods Pvt. Ltd.,", "Survey No. 112, G.T. Karnal Road,", "Karnal, Haryana - 132001, India."],
        fssai="10826999000212",
        care=["Consumer Care Cell", "Phone: 1800 180 4455 (Toll Free)", "Email: care@annavia.example.in"],
        mrp_line="M.R.P. ₹745.00", price_lines=[("(Incl. of all taxes)", False), ("Unit Sale Price:", False),
                                                  ("₹149.00 per kg", True)],
        stamp=["PKD: 07/2026", "BEST BEFORE: 01/2028", "BATCH NO: AN2607R"],
        side_text=["Best Before 18 months", "from packing.", "", "Store in a cool, dry", "place away from", "moisture.", "",
                   "Rinse twice before", "cooking."],
        category="food", commodity="Basmati Rice", expect="All declarations detected - Needs verification (physical checks only)"),
    "sunflower_oil_1l": dict(
        brand="SUNVELA", tag="REFINED", name_lines=["SUNFLOWER OIL"], shape="bottle", cap=(200, 40, 40),
        color=(236, 190, 30), dark=(110, 70, 10), accent=(240, 180, 20), accent_text=(170, 90, 20), illo="oil", veg=True,
        claims=["Light & Healthy", "Rich in Vitamin E"], front_qty="Net Vol. 1 L",
        nutrition=("Nutritional Information", "(Approx. values per 100 ml)",
                   [("Energy", "828 kcal"), ("Total Fat", "92.0 g"), ("Saturated Fat", "10.0 g"), ("Trans Fat", "0.0 g"),
                    ("Vitamin E", "25 mg")]),
        ingredients_label="Ingredients:", ingredients=["Refined Sunflower Oil,", "Antioxidant (INS 319)."],
        mfr_label="Manufactured by:",
        mfr=["Sunvela Edible Oils Pvt. Ltd.,", "Plot 7, APIIC Industrial Park,", "Kakinada, Andhra Pradesh - 533003,",
             "India."],
        fssai="10126999000388",
        care=["Customer Care Executive", "Phone: 1800 425 6677 (Toll Free)", "Email: care@sunvela.example.in"],
        mrp_line="M.R.P. ₹185.00", price_lines=[("(Incl. of all taxes)", False), ("Unit Sale Price:", False),
                                                  ("₹185.00 per L", True)],
        stamp=["PKD: 06/2026", "USE BY: 03/2027", "BATCH NO: SV2606K"],
        side_text=["Best Before 9 months", "from packing.", "", "Store in a cool, dry", "place away from direct",
                   "sunlight."],
        category="food", commodity="Sunflower Oil", expect="All declarations detected - Needs verification (physical checks only)"),
    "cookies_200g_defective": dict(
        brand="CRUNCHOLA", tag="BUTTER", name_lines=["COOKIES"], shape="pouch",
        color=(196, 60, 50), dark=(120, 30, 24), accent=(196, 60, 50), accent_text=(170, 110, 40), illo="cookies", veg=True,
        claims=["Baked with real butter", "Crunchy & Delicious"], front_qty="Net Wt. approx. 200 gms",
        nutrition=("Nutritional Information", "(Approx. values per 100 g)",
                   [("Energy", "495 kcal"), ("Protein", "6.5 g"), ("Carbohydrate", "66.0 g"), ("Total Fat", "22.5 g")]),
        ingredients_label="Ingredients:",
        ingredients=["Refined Wheat Flour (Maida), Sugar,", "Butter (12%), Edible Vegetable Oil,",
                     "Milk Solids, Salt, Raising Agents."],
        mfr_label="Manufactured by:",
        mfr=["Crunchola Bakes Pvt. Ltd.,", "Plot 33, SIDCO Industrial Estate,", "Coimbatore, Tamil Nadu - 641021, India."],
        fssai="10026999000519", care=None, back_extra=["Visit us: www.crunchola.example.in"],
        mrp_line="M.R.P. ₹40.00", price_lines=[("+ local taxes extra", False)],
        stamp=["PKD: 08/2026", "BATCH NO: CR2608D"],
        side_text=["Store in a cool, dry", "place.", "", "Once opened, keep in", "an airtight container."],
        category="food", commodity="Butter Cookies",
        expect="Deliberately defective - potential NON-COMPLIANT findings: 'approx.' qualifier, non-standard unit 'gms', "
               "'+ local taxes extra' with the MRP, no best-before / expiry date, no consumer-care details, no unit sale price"),
    "herbal_shampoo_340ml": dict(
        brand="NEELARA", tag="HERBAL", name_lines=["ANTI-HAIRFALL", "SHAMPOO"], shape="bottle", cap=(40, 90, 60),
        color=(90, 150, 110), dark=(30, 80, 50), accent=(60, 140, 80), accent_text=(40, 110, 70), illo="leaves", veg=None,
        claims=["With Bhringraj & Amla", "For Strong, Healthy Hair"], front_qty="340 ml",
        nutrition=None,
        ingredients_label="Ingredients:",
        ingredients=["Aqua, Sodium Laureth Sulfate,", "Cocamidopropyl Betaine, Glycerin,", "Bhringraj Extract, Amla Extract,",
                     "Sodium Chloride, Fragrance."],
        mfr_label="Manufactured & Marketed by:",
        mfr=["Neelara Personal Care Pvt. Ltd.,", "Unit 4, Sector 11, IIE SIDCUL,", "Haridwar, Uttarakhand - 249403, India."],
        fssai=None,
        care=["Customer Care Manager", "Phone: 1800 270 3344 (Toll Free)", "Email: care@neelara.example.in"],
        mrp_line="M.R.P. ₹299.00", price_lines=[("(Incl. of all taxes)", False), ("Unit Sale Price:", False),
                                                  ("₹87.94 per 100 ml", True)],
        stamp=["MFD: 05/2026", "USE BEFORE: 04/2029", "BATCH NO: NS2605C"],
        side_text=["Directions: Apply on", "wet hair, massage", "gently and rinse.", "", "For external use only.",
                   "Avoid contact with eyes."],
        category="cosmetic", commodity="Shampoo", expect="All declarations detected - Needs verification (physical checks only)"),
    "detergent_powder_1kg": dict(
        brand="WASHORA", tag="MATIC", name_lines=["DETERGENT POWDER"], shape="pouch",
        color=(40, 90, 190), dark=(20, 50, 120), accent=(60, 120, 220), accent_text=(200, 60, 40), illo="bubbles", veg=None,
        claims=["Tough on stains", "Gentle on clothes"], front_qty="Net Wt. 1 kg",
        nutrition=None,
        ingredients_label="Composition:",
        ingredients=["Anionic Surfactants (15-30%),", "Sodium Carbonate, Sodium Sulphate,", "Enzymes, Optical Brightener,",
                     "Perfume."],
        mfr_label="Manufactured & Packed by:",
        mfr=["Washora Home Care Pvt. Ltd.,", "Plot 58, GIDC Estate, Vatva,", "Ahmedabad, Gujarat - 382445, India."],
        fssai=None,
        care=["Consumer Care Manager", "Phone: 1800 233 9911 (Toll Free)", "Email: care@washora.example.in"],
        mrp_line="M.R.P. ₹120.00", price_lines=[("(Incl. of all taxes)", False), ("Unit Sale Price:", False),
                                                  ("₹120.00 per kg", True)],
        stamp=["MFD: 08/2026", "BATCH NO: WD2608K"],
        side_text=["Directions: Use 1 scoop", "for a full load.", "", "Keep out of reach of", "children. Wash hands",
                   "after use.", "", "Store in a dry place."],
        category="household", commodity="Detergent Powder", expect="All declarations detected - Needs verification (physical checks only)"),
}


def main():
    for key, p in PRODUCTS.items():
        out = SAMPLES / key
        out.mkdir(parents=True, exist_ok=True)
        photos = []
        for i, (side, fn, lit) in enumerate((("front", front_panel, True), ("back", back_panel, True),
                                             ("left", side_panel, False))):
            q = pack_photo(fn(p), p, 10 * i + 1, lit)
            exif = Image.Exif()
            exif[0x010E] = "SYNTHETIC SAMPLE - NOT A REAL PRODUCT (SafeMetric demo)"
            q.save(out / f"{side}.jpg", "JPEG", quality=92, exif=exif)
            photos.append(q)
        overview(photos).save(SAMPLES / f"{key}_overview.jpg", "JPEG", quality=88)
        print("wrote", out)


if __name__ == "__main__":
    main()
