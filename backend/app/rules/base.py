"""
Deterministic rule-engine primitives.

Every check has a fixed specification (rule number, title, applicability, required data,
validation condition, verification requirement) and returns exactly one of

    PASS | NON_COMPLIANT | NEEDS_VERIFICATION | NOT_APPLICABLE

together with a human-readable reason and the OCR evidence it relied on.
No machine-learning model participates in the decision.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

PASS = "PASS"
NON_COMPLIANT = "NON_COMPLIANT"
NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
NOT_APPLICABLE = "NOT_APPLICABLE"
STATUSES = (PASS, NON_COMPLIANT, NEEDS_VERIFICATION, NOT_APPLICABLE)

CONFIG_DIR = Path(__file__).resolve().parent / "config"


@lru_cache
def load_config(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def category_config(category: str) -> dict:
    path = CONFIG_DIR / f"{category}_rules.json"
    if not path.exists():
        path = CONFIG_DIR / "other_rules.json"
    return load_config(path.name)


def available_categories() -> list[dict]:
    out = []
    for p in sorted(CONFIG_DIR.glob("*_rules.json")):
        if p.name == "common_rules.json":
            continue
        c = load_config(p.name)
        out.append({"key": c["category"], "label": c["label"]})
    order = ["food", "beverage", "cosmetic", "personal_care", "household", "electronics", "electrical",
             "textile", "hardware", "stationery", "pharmaceutical", "other"]
    return sorted(out, key=lambda c: order.index(c["key"]) if c["key"] in order else 99)


@dataclass
class CheckSpec:
    check_id: str
    rule_no: str
    rule_title: str
    title: str
    reference: str
    severity: str                      # HIGH | MEDIUM | LOW
    applicability: str
    required_data: list[str]
    condition: str
    verification: str = ""
    description: str = ""

    def to_dict(self):
        return asdict(self)

    def result(self, status: str, reason: str, evidence: list | None = None, recommendation: str = "",
               applicable: bool = True, verification: str | None = None) -> "CheckResult":
        assert status in STATUSES
        return CheckResult(spec=self, status=status, reason=reason, evidence=evidence or [],
                           recommendation=recommendation, applicable=applicable and status != NOT_APPLICABLE,
                           verification=self.verification if verification is None else verification)


@dataclass
class CheckResult:
    spec: CheckSpec
    status: str
    reason: str
    evidence: list = field(default_factory=list)
    recommendation: str = ""
    applicable: bool = True
    verification: str = ""

    def to_dict(self, weight: float = 1.0) -> dict:
        s = self.spec
        return {"check_id": s.check_id, "rule_no": s.rule_no, "rule_title": s.rule_title, "title": s.title,
                "reference": s.reference, "severity": s.severity, "weight": weight, "applicable": self.applicable,
                "applicability": s.applicability, "required_data": s.required_data, "condition": s.condition,
                "status": self.status, "reason": self.reason, "verification": self.verification,
                "evidence": self.evidence, "recommendation": self.recommendation}


@dataclass
class ImageInfo:
    id: int
    name: str
    side: str
    quality_status: str
    width: int
    height: int
    panel_width_mm: float | None
    panel_height_mm: float | None
    mean_confidence: float
    lines: list
    load_gray: Callable | None = None   # lazily returns the display image as grayscale ndarray


@dataclass
class RuleContext:
    category: str
    is_imported: bool
    registration_number: str
    all_panels_captured: bool
    inspection_date: object              # datetime
    product_name: str
    fields: dict                          # field name -> FieldResult
    images: list[ImageInfo]
    category_cfg: dict
    common: dict
    registration_verifier: object = None

    # ---------------------------------------------------------------- helpers
    def field(self, name):
        return self.fields.get(name)

    def image(self, image_id) -> ImageInfo | None:
        return next((i for i in self.images if i.id == image_id), None)

    def evidence(self, *names: str) -> list[dict]:
        out = []
        for n in names:
            f = self.fields.get(n)
            if f and f.found:
                out.append({"field": n, "label": f.label, "text": f.evidence, "value": f.value,
                            "confidence": f.confidence, "image_id": f.source_image_id, "image": f.source_image,
                            "side": f.source_side, "bbox": f.bbox})
        return out

    @property
    def mean_ocr_confidence(self) -> float:
        vals = [i.mean_confidence for i in self.images if i.mean_confidence]
        return sum(vals) / len(vals) if vals else 0.0

    def coverage_is_conclusive(self) -> bool:
        """True when a declaration that was not found can be treated as genuinely absent."""
        cfg = self.common["missing_declaration"]
        if not cfg.get("allow_non_compliant_from_ocr_absence", False):
            return False                     # absence is never proven by OCR alone (see common_rules.json)
        return (self.all_panels_captured and bool(self.images)
                and all(i.quality_status != "POOR" for i in self.images)
                and self.mean_ocr_confidence >= cfg["min_mean_ocr_confidence"])

    def coverage_statement(self) -> str:
        n = len(self.images)
        return f"{n} image{'s' if n != 1 else ''} analysed ({', '.join(sorted({i.side for i in self.images}))})"

    def missing(self, spec: CheckSpec, what: str, recommendation: str, partial_note: str = "") -> CheckResult:
        """Standard handling for a declaration that could not be confirmed."""
        f_note = f" {partial_note}" if partial_note else ""
        if self.coverage_is_conclusive() and not partial_note:
            return spec.result(NON_COMPLIANT,
                               f"{what} was not found on any of the photographed panels. The inspector confirmed "
                               f"that all label panels were captured, image quality is adequate and mean OCR "
                               f"confidence is {self.mean_ocr_confidence:.0f}% ({self.coverage_statement()}).",
                               recommendation=recommendation)
        return spec.result(NEEDS_VERIFICATION,
                           f"{what} was not found in the OCR text of the uploaded images.{f_note} "
                           f"Potential finding: absence cannot be concluded from OCR alone ({self.coverage_statement()}); "
                           f"confirm on the physical package.",
                           recommendation=recommendation,
                           verification="Physically examine all panels of the package for this declaration.")


class Rule:
    """Base class: subclasses declare `rule_no`, `title`, `checks` and implement evaluate()."""
    rule_no: str = ""
    title: str = ""
    checks: list[CheckSpec] = []

    def evaluate(self, ctx: RuleContext) -> list[CheckResult]:  # pragma: no cover - abstract
        raise NotImplementedError

    def spec(self, check_id: str) -> CheckSpec:
        return next(c for c in self.checks if c.check_id == check_id)
