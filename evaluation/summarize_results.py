"""
Collect every evaluation result into evaluation/results/SUMMARY.md (markdown tables).

    python evaluation/summarize_results.py [--split test]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evaluation" / "results"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(v, d=1):
    return "—" if v is None else f"{100 * v:.{d}f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    ap.add_argument("--tags", default="tesseract_original,ppocr_auto,hybrid_auto")
    a = ap.parse_args()
    tags = a.tags.split(",")
    out = [f"# SafeMetric evaluation summary ({a.split} split, synthetic data)", "",
           "All numbers were produced by the scripts in `evaluation/` on the synthetic dataset. They show how the "
           "system behaves on these labels; they do not guarantee accuracy on real packaging.", ""]

    # ---------------------------------------------------------------- OCR
    out += ["## OCR (text detection + recognition)", "",
            "| Engine configuration | Images | Det. P | Det. R | Det. F1 | CER ↓ | WER ↓ | Word recall | Numeric recall | CER (Hindi+English lines) | s / image |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    ocr = {}
    for t in tags:
        d = load(RES / f"ocr_{t}_{a.split}.json")
        if not d:
            continue
        o = d["summary"]["overall"]
        ocr[t] = d
        out.append(f"| `{t}` | {o['images']} | {pct(o['det_precision'])} | {pct(o['det_recall'])} | {pct(o['det_f1'])} | "
                   f"{pct(o.get('cer_en'))} | {pct(o.get('wer_en'))} | {pct(o['bow_recall'])} | "
                   f"{pct(o['numeric_token_recall'])} | {pct(o.get('cer_mixed'))} | {o['seconds_per_image']} |")
    if ocr:
        conds = sorted({c for d in ocr.values() for c in d["summary"]["by_condition"]})
        out += ["", "### CER by capture condition (lower is better)", "",
                "| Condition | " + " | ".join(f"`{t}`" for t in ocr) + " | images |", "|---" * (len(ocr) + 2) + "|"]
        for c in conds:
            row = [pct(d["summary"]["by_condition"].get(c, {}).get("cer_en")) for d in ocr.values()]
            n = next(iter(ocr.values()))["summary"]["by_condition"].get(c, {}).get("images", "")
            out.append(f"| {c} | " + " | ".join(row) + f" | {n} |")
        out += ["", "### CER by declaration (lines of each field type)", "",
                "| Field | " + " | ".join(f"`{t}`" for t in ocr) + " |", "|---" * (len(ocr) + 1) + "|"]
        fields = sorted({f for d in ocr.values() for f in d["summary"]["cer_by_field"]})
        for f in fields:
            out.append(f"| {f} | " + " | ".join(pct(d["summary"]["cer_by_field"].get(f)) for d in ocr.values()) + " |")

    same = load(RES / f"ocr_engine_comparison_same150_{a.split}.json")
    if same:
        out += ["", f"### Paired comparison on the same {len(same['images'])} test images (the hybrid engine was run on "
                "these only)", "", "| Engine | Det. F1 | CER | WER | Numeric recall | Field micro-F1 (model) | Doc exact | s / image |",
                "|---|---|---|---|---|---|---|---|"]
        for t, o in same["results"].items():
            ex = load(RES / f"same150_extraction_{t}_model.json")
            eo = ex["overall"] if ex else {}
            out.append(f"| `{t}` | {pct(o['det_f1'])} | {pct(o.get('cer_en'))} | {pct(o.get('wer_en'))} | "
                       f"{pct(o['numeric_token_recall'])} | {pct(eo.get('micro_f1'))} | {pct(eo.get('document_exact_match'))} | "
                       f"{o['seconds_per_image']} |")

    # ---------------------------------------------------------------- extraction
    out += ["", "## Structured field extraction", ""]
    rows = []
    for p in sorted(RES.glob(f"extraction_*_{a.split}.json")):
        d = load(p)
        o = d["overall"]
        rows.append((p.stem.replace(f"_{a.split}", ""), d, o))
    if rows:
        out += ["| Run | Docs | Micro P | Micro R | Micro F1 | Macro F1 | Document exact match |", "|---|---|---|---|---|---|---|"]
        for name, d, o in rows:
            out.append(f"| `{name}` | {o['documents']} | {pct(o['micro_precision'])} | {pct(o['micro_recall'])} | "
                       f"{pct(o['micro_f1'])} | {pct(o['macro_f1'])} | {pct(o['document_exact_match'])} |")
        for name, d, o in rows:
            out += ["", f"### Per field - `{name}`", "", "| Field | Precision | Recall | F1 | Accuracy | Support |",
                    "|---|---|---|---|---|---|"]
            for f, v in o["per_field"].items():
                out.append(f"| {f} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} | {pct(v['accuracy'])} | {v['support']} |")
            if d["mode"] == "text":
                out += ["", "| Noise level | Micro F1 | Exact match | n |", "|---|---|---|---|"]
                for k, v in d["groups"].items():
                    out.append(f"| {k} | {pct(v['micro_f1'])} | {pct(v['document_exact_match'])} | {v['documents']} |")

    # ---------------------------------------------------------------- compliance
    for p in sorted(RES.glob(f"compliance_*_{a.split}.json")):
        d = load(p)
        out += ["", f"## Compliance analysis - `{p.stem}`", "",
                f"Images: {d['images']} · image quality grades: {d.get('image_quality_grades')} · status agreement "
                f"OCR vs perfect-text oracle: {pct(d['status_agreement_ocr_vs_oracle'])}", "",
                "| Injected defect | Check | Cases | Flagged (oracle) | Flagged (OCR) | NON_COMPLIANT (OCR) |",
                "|---|---|---|---|---|---|"]
        for k, v in d["ocr"]["per_defect"].items():
            ov = d["oracle"]["per_defect"].get(k, {})
            out.append(f"| {k} | {v['check']} | {v['observable_cases']} | {pct(ov.get('flagged_rate'))} | "
                       f"{pct(v['flagged_rate'])} | {pct(v['non_compliant_rate'])} |")
        out += ["", f"* Overall flagged: oracle {pct(d['oracle']['overall_flagged_rate'])}, OCR {pct(d['ocr']['overall_flagged_rate'])}",
                f"* False NON_COMPLIANT on {d['ocr']['clean_full_labels']} defect-free fully photographed labels: "
                f"oracle {pct(d['oracle']['false_non_compliant_rate_any'])}, OCR {pct(d['ocr']['false_non_compliant_rate_any'])} "
                f"(by check: {d['ocr']['false_non_compliant_by_check']})"]
    card = load(ROOT / "models" / "extraction" / "line_role_model_card.json")
    if card:
        out += ["", "## Line-role model selection (validation split)", "", "| Data mix | C | Train lines | Val macro-F1 (all roles) | Val brand acc. | Val product acc. |",
                "|---|---|---|---|---|---|"]
        for g in card["grid"]:
            s = g["val_selection_accuracy"]
            out.append(f"| {g['mix']} | {g['C']} | {g['train_lines']} | {pct(g['val_macro_f1_lines'])} | "
                       f"{pct(s.get('brand_name'))} | {pct(s.get('product_name'))} |")
        out.append(f"\nSelected: {card['selected']} · thresholds {card['thresholds']}")
    (RES / "SUMMARY.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
