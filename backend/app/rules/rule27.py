"""
Rule 27 - Registration of manufacturers / packers / importers.

Registration status cannot be established from a package photograph. This rule therefore
never passes on OCR alone - it delegates to a RegistrationVerifier. The default verifier
reports that no authoritative source is configured; set REGISTRATION_API_URL to plug in an
official registry API (see app/services/registration.py).
"""
from __future__ import annotations

from .base import NEEDS_VERIFICATION, NON_COMPLIANT, PASS, CheckSpec, Rule, RuleContext

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 27"
T = "Registration of manufacturers, packers and importers"
NO_AUTHORITY = "Needs authoritative registration data; image alone is insufficient."


class Rule27(Rule):
    rule_no = "27"
    title = T
    checks = [CheckSpec(
        "R27_REGISTRATION", "27", T, "Registration of the manufacturer / packer / importer", REF, "MEDIUM",
        "Manufacturers, packers and importers of pre-packaged commodities",
        ["registration_number (inspector input or label)", "authoritative registry"],
        "The registration number is confirmed as valid by an authoritative registration source.",
        "Verify registration with the Legal Metrology registration records.")]

    def evaluate(self, ctx: RuleContext):
        s = self.checks[0]
        number = (ctx.registration_number or "").strip()
        source = "entered by the inspector"
        ev = []
        lf = ctx.field("registration_number")
        if not number and lf and lf.found:
            number, source, ev = lf.value, "read from the label", ctx.evidence("registration_number")
        if not number:
            return [s.result(NEEDS_VERIFICATION, f"No registration number was provided or detected. {NO_AUTHORITY}",
                             recommendation="Record the registration number and verify it against official records.")]
        verifier = ctx.registration_verifier
        result = verifier.verify(number) if verifier else {"available": False}
        if not result.get("available"):
            return [s.result(NEEDS_VERIFICATION, f"Registration number '{number}' ({source}). {NO_AUTHORITY}", ev)]
        if result.get("valid"):
            return [s.result(PASS, f"Registration number '{number}' confirmed by {result.get('source', 'registry')}: "
                             f"{result.get('detail', 'valid')}.", ev, verification="")]
        return [s.result(NON_COMPLIANT, f"Registration number '{number}' was reported as NOT valid by "
                         f"{result.get('source', 'registry')}: {result.get('detail', '')}.", ev,
                         "Obtain / renew registration under Rule 27.")]
