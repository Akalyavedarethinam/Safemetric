"""
Synthetic OCR-noise model used to build the field-extraction dataset from ground-truth text.

The confusions mirror what we measured from Tesseract and PP-OCR on real / synthetic labels:
missing spaces ("BatchNo:"), letter-spaced labels ("M R P"), O/0, I/1/l, S/5, B/8 swaps,
the rupee glyph read as 7 / 2 / % / Rs, dropped punctuation, broken or merged lines and
reading-order swaps. Levels: clean < light < medium < heavy.
"""
from __future__ import annotations

import random
import re

CONF = {"0": "O", "O": "0", "1": "I", "I": "1", "l": "1", "5": "S", "S": "5", "8": "B", "B": "8", "2": "Z",
        "6": "G", "g": "9", "rn": "m", "m": "rn", "cl": "d", ".": ",", ",": "."}
RUPEE = ["₹", "7", "2", "%", "Rs", "R", "F", "="]
LEVEL = {"clean": 0.0, "light": 0.015, "medium": 0.04, "heavy": 0.09}


def _char_noise(t: str, p: float, rng: random.Random) -> str:
    out, i = [], 0
    while i < len(t):
        ch = t[i]
        r = rng.random()
        if ch == "₹":
            out.append(rng.choice(RUPEE) if r < p * 12 else ch)
        elif r < p * 0.35 and t[i:i + 2] in CONF:
            out.append(CONF[t[i:i + 2]]); i += 2; continue
        elif r < p * 0.7 and ch in CONF:
            out.append(CONF[ch])
        elif r < p * 0.8 and ch == " ":
            pass                                   # dropped space
        elif r < p * 0.88:
            pass                                   # dropped char
        elif r < p * 0.93:
            out.append(ch); out.append(rng.choice(".,'-:|"))
        elif r < p * 1.0 and ch.isalpha():
            out.append(ch.swapcase())
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _label_spacing(t: str, rng: random.Random) -> str:
    def spaced(m):
        return " ".join(m.group(0))
    return re.sub(r"\b(MRP|NET|WT|FSSAI|BATCH|PKD|MFG|EXP)\b", spaced, t) if rng.random() < 0.5 else t


def _glue(t: str, rng: random.Random) -> str:
    # PP-OCR style: drop spaces around ':' and between label words
    t = re.sub(r"\s*:\s*", ":", t) if rng.random() < 0.5 else t
    return re.sub(r"(?<=[a-z]) (?=[A-Z])", "", t) if rng.random() < 0.5 else t


def noisy_lines(lines: list[dict], level: str, rng: random.Random) -> tuple[list[dict], set]:
    """lines: [{'text', 'fields', 'size', ...}] -> (noisy lines, fields whose line was dropped entirely).

    The ground truth itself is never changed; fields whose only evidence was dropped are reported
    so the scorer can exclude them (that is a detection miss, not an extraction error)."""
    p = LEVEL[level]
    out = []
    for ln in lines:
        t = ln["text"]
        if level != "clean":
            t = _char_noise(t, p, rng)
            if rng.random() < p * 4:
                t = _label_spacing(t, rng)
            if rng.random() < p * 6:
                t = _glue(t, rng)
        out.append({**ln, "text": t})
    if level in ("medium", "heavy"):
        # line split / merge / local order swap
        i = 0
        res = []
        while i < len(out):
            ln = out[i]
            r = rng.random()
            if r < p * 2 and len(ln["text"]) > 25:
                k = ln["text"].find(" ", len(ln["text"]) // 2)
                if k > 0:
                    res += [{**ln, "text": ln["text"][:k]}, {**ln, "text": ln["text"][k + 1:], "split_part": True}]
                    i += 1
                    continue
            if r < p * 3 and i + 1 < len(out) and len(ln["text"]) + len(out[i + 1]["text"]) < 70:
                res.append({**ln, "text": ln["text"] + "  " + out[i + 1]["text"], "merged_with": out[i + 1].get("field")})
                i += 2
                continue
            res.append(ln)
            i += 1
        if len(res) > 3 and rng.random() < p * 5:
            j = rng.randrange(len(res) - 1)
            res[j], res[j + 1] = res[j + 1], res[j]
        out = res
    dropped: set = set()
    if level == "heavy" and out and rng.random() < 0.3:
        gone = out.pop(rng.randrange(len(out)))   # a whole line missed by the detector
        dropped |= set(gone.get("fields") or [gone.get("field")])
    return out, dropped
