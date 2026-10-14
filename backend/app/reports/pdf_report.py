"""A4 PDF inspection report (ReportLab)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from ..models import Inspection
from .common import (DISCLAIMER, FIELD_STATUS_LABEL, LEGEND, STATUS_HEX, STATUS_LABEL, crop_bytes, image_bytes,
                     meta)
from ..rules.registry import OVERALL_LABELS

NAVY = colors.HexColor("#0b1f3a")
BLUE = colors.HexColor("#1d4ed8")
LIGHT = colors.HexColor("#f1f5f9")
LINE = colors.HexColor("#cbd5e1")


def _register_fonts() -> tuple[str, str]:
    """Use DejaVu (has the ₹ glyph) when available; fall back to Helvetica."""
    for base in ("/usr/share/fonts/truetype/dejavu/", str(Path(__file__).parent / "fonts") + "/"):
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", base + "DejaVuSans.ttf"))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", base + "DejaVuSans-Bold.ttf"))
            return "DejaVu", "DejaVu-Bold"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


def _styles(regular, bold):
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName=bold, fontSize=20, textColor=NAVY, spaceAfter=2),
        "sub": ParagraphStyle("s", fontName=bold, fontSize=9.5, textColor=BLUE, alignment=TA_CENTER, spaceAfter=2),
        "subsmall": ParagraphStyle("ss", fontName=regular, fontSize=7.5, textColor=colors.HexColor("#475569"), alignment=TA_CENTER),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11.5, textColor=NAVY, spaceBefore=10, spaceAfter=5),
        "b": ParagraphStyle("b", fontName=regular, fontSize=8, leading=10.2),
        "bb": ParagraphStyle("bb", fontName=bold, fontSize=8, leading=10.2),
        "small": ParagraphStyle("sm", fontName=regular, fontSize=6.8, leading=8.4, textColor=colors.HexColor("#475569")),
        "cell_w": ParagraphStyle("cw", fontName=bold, fontSize=7.6, leading=9.5, textColor=colors.white),
    }


def _esc(s) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _status_para(status, st, label=None):
    hexc = STATUS_HEX.get(status, "#334155")
    text = label or STATUS_LABEL.get(status) or FIELD_STATUS_LABEL.get(status) or status
    return Paragraph(f'<font color="{hexc}"><b>{_esc(text).upper()}</b></font>', st["small"])


def build(insp: Inspection, generated_by: str = "") -> bytes:
    regular, bold = _register_fonts()
    st = _styles(regular, bold)
    buf = io.BytesIO()
    now = datetime.now(timezone.utc)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(15 * mm, 10 * mm, f"SafeMetric · {insp.reference} · generated {now:%d-%b-%Y %H:%M} UTC"
                                            + (f" by {generated_by}" if generated_by else ""))
        canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}  ·  integrity SHA-256 {insp.integrity_hash[:16]}…")
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(2)
        canvas.line(15 * mm, 287 * mm, 195 * mm, 287 * mm)
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"SafeMetric report {insp.reference}",
                            author="SafeMetric", subject="Legal Metrology compliance inspection report")
    el = [Paragraph("SAFEMETRIC", st["title"]),
          Paragraph("LEGAL METROLOGY COMPLIANCE INSPECTION REPORT", st["sub"]),
          Paragraph("The Legal Metrology Act, 2009 · Legal Metrology (Packaged Commodities) Rules, 2011", st["subsmall"]),
          Spacer(1, 8)]

    # ---------------------------------------------------------------- header table
    m = meta(insp)
    rows = []
    for i in range(0, len(m), 2):
        pair = m[i:i + 2]
        row = []
        for k, v in pair:
            if k == "Overall status":
                row += [Paragraph(f"<b>{k}</b>", st["b"]), Paragraph(f"<b>{_esc(v).upper()}</b>", st["cell_w"])]
            else:
                row += [Paragraph(f"<b>{k}</b>", st["b"]), Paragraph(_esc(v), st["b"])]
        rows.append(row + [""] * (4 - len(row)))
    t = Table(rows, colWidths=[33 * mm, 57 * mm, 33 * mm, 57 * mm])
    style = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (0, -1), LIGHT),
             ("BACKGROUND", (2, 0), (2, -1), LIGHT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    idx = next(i for i, (k, _) in enumerate(m) if k == "Overall status")
    cell = ((idx % 2) * 2 + 1, idx // 2)
    style.append(("BACKGROUND", cell, cell, colors.HexColor(STATUS_HEX.get(insp.overall_status, "#334155"))))
    t.setStyle(TableStyle(style))
    el.append(t)
    el.append(Spacer(1, 5))

    counts = [("PASSED CHECKS", insp.passed, "#dcfce7"), ("NON-COMPLIANT", insp.failed, "#fee2e2"),
              ("NEEDS VERIFICATION", insp.needs_verification, "#fef3c7"), ("NOT APPLICABLE", insp.not_applicable, "#f1f5f9"),
              ("OCR CONFIDENCE", f"{insp.ocr_confidence:.1f}%", "#dbeafe")]
    ct = Table([[Paragraph(f"<b>{k}: {v}</b>", st["b"]) for k, v, _ in counts]], colWidths=[36 * mm] * 5)
    ct.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE)] +
                           [("BACKGROUND", (i, 0), (i, 0), colors.HexColor(c)) for i, (_, _, c) in enumerate(counts)]))
    el.append(ct)
    reason = (insp.summary or {}).get("overall_reason", "")
    if reason:
        el += [Spacer(1, 4), Paragraph(f"<b>Basis of overall status:</b> {_esc(reason)} "
                                       f"Status rules: any high-severity non-compliance → Non-Compliant; other "
                                       f"non-compliance → Partially Compliant; otherwise any unverifiable check → "
                                       f"Needs Verification.", st["small"])]

    # ---------------------------------------------------------------- 1. images
    el.append(Paragraph("1. Physical packaging label - photographic evidence", st["h"]))
    img_cells = []
    for img in insp.images:
        boxes = [f.bbox for f in insp.fields if f.source_image_id == img.id and f.bbox and f.status != "NOT_DETECTED"]
        data = image_bytes(img, boxes=boxes, max_side=700)
        pic = Image(io.BytesIO(data), width=52 * mm, height=52 * mm, kind="proportional") if data else Paragraph("image unavailable", st["small"])
        q = img.quality or {}
        cap = (f"<b>{img.side.upper()}</b> · {_esc(img.original_filename)}<br/>{img.width}×{img.height}px · "
               f"{img.size_bytes / 1024:.0f} KB · quality <b>{img.quality_status or '-'}</b><br/>"
               f"OCR {img.ocr.mean_confidence if img.ocr else 0:.1f}% · SHA-256 {img.sha256[:12]}…")
        if q.get("warnings"):
            cap += f"<br/><font color='#b45309'>{_esc('; '.join(q['warnings'][:2]))}</font>"
        img_cells.append([pic, Paragraph(cap, st["small"])])
    grid = []
    for i in range(0, len(img_cells), 3):
        chunk = img_cells[i:i + 3]
        grid.append([c[0] for c in chunk] + [""] * (3 - len(chunk)))
        grid.append([c[1] for c in chunk] + [""] * (3 - len(chunk)))
    if grid:
        g = Table(grid, colWidths=[60 * mm] * 3)
        g.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BOX", (0, 0), (-1, -1), 0.4, LINE)]))
        el.append(g)
        el.append(Paragraph("Blue rectangles mark the locations of detected declarations. Images are shown after "
                            "orientation correction; the original uploads are retained unaltered (SHA-256 recorded).",
                            st["small"]))

    # ---------------------------------------------------------------- 2. extracted declarations
    el.append(Paragraph("2. Declarations extracted from the label (OCR - detected, not verified)", st["h"]))
    hdr = ["Declaration", "Extracted value", "Conf.", "Source", "Extraction status"]
    data = [[Paragraph(f"<b>{h}</b>", st["cell_w"]) for h in hdr]]
    for f in insp.fields:
        if f.status == "NOT_DETECTED" and f.field not in ("manufacturer_packer", "importer", "generic_name", "net_quantity",
                                                            "mrp", "mfg_date", "best_before", "consumer_care",
                                                            "country_of_origin", "unit_sale_price"):
            continue
        data.append([Paragraph(_esc(f.label), st["bb"]), Paragraph(_esc(f.value or "- not detected -"), st["b"]),
                     Paragraph(f"{f.confidence:.0f}%" if f.confidence else "-", st["b"]),
                     Paragraph(_esc(f"{f.source_side} · {f.source_image}" if f.source_image else "-"), st["small"]),
                     _status_para(f.status, st)])
    t = Table(data, colWidths=[38 * mm, 62 * mm, 13 * mm, 35 * mm, 32 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]))
    el.append(t)

    # ---------------------------------------------------------------- 3. rule findings
    el.append(Paragraph("3. Deterministic rule evaluation", st["h"]))
    hdr = ["Rule", "Check", "Sev.", "Result", "Reason / evidence"]
    data = [[Paragraph(f"<b>{h}</b>", st["cell_w"]) for h in hdr]]
    for f in insp.findings:
        ev = ""
        if f.evidence:
            ev = "<br/><font color='#475569'>Evidence: " + _esc(" | ".join(
                f"“{e.get('text', '')[:90]}” ({e.get('side', '')}, {e.get('confidence', 0):.0f}%)" for e in f.evidence[:2])) + "</font>"
        data.append([Paragraph(_esc(f.rule_no), st["bb"]), Paragraph(_esc(f.title), st["b"]),
                     Paragraph(f.severity, st["small"]), _status_para(f.status, st),
                     Paragraph(_esc(f.reason) + ev, st["small"])])
    t = Table(data, colWidths=[14 * mm, 42 * mm, 15 * mm, 29 * mm, 80 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]))
    el.append(t)

    # ---------------------------------------------------------------- 4. violations & actions
    nc = [f for f in insp.findings if f.status == "NON_COMPLIANT"]
    nv = [f for f in insp.findings if f.status == "NEEDS_VERIFICATION"]
    el.append(Paragraph("4. Violation summary and required actions", st["h"]))
    if nc:
        rows = [[Paragraph("<b>Non-compliant finding</b>", st["cell_w"]), Paragraph("<b>Statutory reference</b>", st["cell_w"]),
                 Paragraph("<b>Directed action</b>", st["cell_w"])]]
        for f in nc:
            rows.append([Paragraph(f"<b>{_esc(f.title)}</b><br/>{_esc(f.reason)}", st["small"]),
                         Paragraph(_esc(f.reference), st["small"]), Paragraph(_esc(f.recommendation), st["small"])])
        t = Table(rows, colWidths=[80 * mm, 45 * mm, 55 * mm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#991b1b")), ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        el.append(t)
    else:
        el.append(Paragraph("No non-compliance was established from the image evidence.", st["b"]))
    if nv:
        el.append(Spacer(1, 4))
        el.append(Paragraph("<b>Items requiring physical / authoritative verification:</b> " +
                            "; ".join(_esc(f"{f.rule_no} – {f.title}") for f in nv), st["small"]))

    # ---------------------------------------------------------------- 5. evidence crops
    crops = []
    img_by_id = {i.id: i for i in insp.images}
    for f in insp.fields:
        if f.status == "NOT_DETECTED" or not f.bbox or f.source_image_id not in img_by_id:
            continue
        data = crop_bytes(img_by_id[f.source_image_id], f.bbox)
        if data:
            crops.append([Paragraph(f"<b>{_esc(f.label)}</b><br/>{_esc(f.source_side)} · {f.confidence:.0f}%", st["small"]),
                          Image(io.BytesIO(data), width=95 * mm, height=16 * mm, kind="proportional"),
                          Paragraph(_esc(f.evidence[:160]), st["small"])])
    if crops:
        el.append(PageBreak())
        el.append(Paragraph("5. OCR evidence - cropped from the package photographs", st["h"]))
        t = Table(crops, colWidths=[35 * mm, 97 * mm, 48 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        el.append(t)

    # ---------------------------------------------------------------- 6. attachments, legend, sign-off
    if insp.attachments:
        el.append(Paragraph("6. Supporting evidence attached by the inspector", st["h"]))
        for a in insp.attachments:
            el.append(Paragraph(f"• {_esc(a.original_filename)} ({a.size_bytes / 1024:.0f} KB) – {_esc(a.caption)} "
                                f"[uploaded by {_esc(a.uploaded_by)}]", st["b"]))
    el.append(Paragraph("Legend - how to read this report", st["h"]))
    lt = Table([[Paragraph(f"<b>{k}</b>", st["b"]), Paragraph(_esc(v), st["small"])] for k, v in LEGEND],
               colWidths=[35 * mm, 145 * mm])
    lt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE), ("BACKGROUND", (0, 0), (0, -1), LIGHT)]))
    el.append(lt)
    el.append(Spacer(1, 6))
    el.append(Paragraph(_esc(DISCLAIMER), st["small"]))
    el.append(Paragraph(f"Record integrity (SHA-256 over images, extracted values and findings): {insp.integrity_hash}",
                        st["small"]))
    el.append(Spacer(1, 18))
    sig = Table([[Paragraph("______________________________<br/>Signature of Inspecting Officer", st["small"]),
                  Paragraph(f"______________________________<br/>Name: {_esc(insp.inspector_name)}", st["small"]),
                  Paragraph("______________________________<br/>Date / Seal", st["small"])]], colWidths=[60 * mm] * 3)
    el.append(KeepTogether(sig))
    doc.build(el, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
