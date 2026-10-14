"""Rule 6 - Declarations to be made on every package."""
from __future__ import annotations

from .base import (NEEDS_VERIFICATION, NON_COMPLIANT, NOT_APPLICABLE, PASS, CheckSpec, Rule,
                   RuleContext)

REF = "Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 6(1)"
T = "Declarations to be made on every package"


def _spec(cid, title, sev, applic, data, cond, verification="", ref=REF):
    return CheckSpec(cid, "6", T, title, ref, sev, applic, data, cond, verification)


class Rule6(Rule):
    rule_no = "6"
    title = T
    checks = [
        _spec("R6_MANUFACTURER", "Name and complete address of manufacturer / packer", "HIGH",
              "All retail packages", ["manufacturer_packer"],
              "A 'manufactured/packed by' declaration with a name and a complete address (PIN code) is present."),
        _spec("R6_IMPORTER", "Name and complete address of importer", "HIGH",
              "Imported packages (inspector marked product as imported)", ["importer"],
              "An 'imported by' declaration with the importer's name and complete address is present."),
        _spec("R6_COMMON_NAME", "Common or generic name of the commodity", "MEDIUM",
              "All retail packages", ["generic_name"],
              "The common/generic name of the commodity is declared."),
        _spec("R6_NET_QUANTITY", "Net quantity declaration", "HIGH",
              "All retail packages", ["net_quantity"],
              "A net quantity with a numeric value and a unit is declared (format checked under Rules 11/12)."),
        _spec("R6_MRP", "Retail sale price (MRP) declaration", "HIGH",
              "All retail packages", ["mrp"],
              "A single, unambiguous MRP amount in Indian Rupees is declared."),
        _spec("R6_MRP_TAXES", "MRP declared inclusive of all taxes", "MEDIUM",
              "All retail packages", ["mrp"],
              "The MRP declaration states it is inclusive of all taxes."),
        _spec("R6_DATE", "Month and year of manufacture / packing / import", "HIGH",
              "All retail packages", ["mfg_date"],
              "A month and year of manufacture, packing or import is declared and is not later than the inspection date."),
        _spec("R6_BEST_BEFORE", "Best before / use by date", "MEDIUM",
              "Commodities that may become unfit for consumption (category configuration: best_before_required)",
              ["best_before", "mfg_date"],
              "A best-before / use-by / expiry declaration is present and is not earlier than the manufacture date."),
        _spec("R6_CONSUMER_CARE", "Consumer care details", "HIGH",
              "All retail packages", ["consumer_care"],
              "Consumer-care contact details (telephone number and/or e-mail) are declared."),
        _spec("R6_ORIGIN", "Country of origin / manufacture", "MEDIUM",
              "Imported packages", ["country_of_origin"],
              "The country of origin or manufacture/assembly is declared."),
        _spec("R6_USP", "Unit sale price", "MEDIUM",
              "Packages sold by weight or volume (category configuration: unit_sale_price_applicable)",
              ["unit_sale_price", "mrp", "net_quantity"],
              "A unit sale price is declared and equals MRP ÷ net quantity (per declared unit) within tolerance."),
    ]

    def evaluate(self, ctx: RuleContext):
        out = []
        f = ctx.field

        # ------------------------------------------------ manufacturer / packer
        spec = self.spec("R6_MANUFACTURER")
        m = f("manufacturer_packer")
        imp = f("importer")
        if m.found and m.status in ("DETECTED", "LOW_CONFIDENCE") and m.normalized.get("pincode"):
            out.append(spec.result(PASS, f"{m.normalized.get('label', 'Manufacturer')} declaration found with a complete "
                                         f"address (PIN {m.normalized['pincode']}).", ctx.evidence("manufacturer_packer")))
        elif m.found:
            out.append(spec.result(NEEDS_VERIFICATION,
                                   "A manufacturer/packer declaration was found but a complete address (PIN code) could "
                                   "not be confirmed from the image." + (f" {m.note}" if m.note else ""),
                                   ctx.evidence("manufacturer_packer"),
                                   "Verify that the full postal address of the manufacturer/packer is printed.",
                                   verification="Physically read the complete address on the package."))
        elif ctx.is_imported and imp.found:
            out.append(spec.result(NOT_APPLICABLE,
                                   "Imported package: the importer's name and address is evaluated under R6_IMPORTER.",
                                   ctx.evidence("importer"), applicable=False))
        else:
            out.append(ctx.missing(spec, "The name and address of the manufacturer/packer",
                                   "Print 'Manufactured/Packed by' with the name and complete address, including PIN code."))

        # ------------------------------------------------ importer
        spec = self.spec("R6_IMPORTER")
        if not ctx.is_imported:
            out.append(spec.result(NOT_APPLICABLE, "Product not marked as imported by the inspector.", applicable=False))
        elif imp.found and imp.normalized.get("pincode"):
            out.append(spec.result(PASS, f"Importer declaration found with complete address (PIN {imp.normalized['pincode']}).",
                                   ctx.evidence("importer")))
        elif imp.found:
            out.append(spec.result(NEEDS_VERIFICATION, "Importer declaration found but the complete address could not be confirmed.",
                                   ctx.evidence("importer"), "Verify the complete address of the importer."))
        else:
            out.append(ctx.missing(spec, "The name and address of the importer",
                                   "Imported packages must declare the importer's name and complete address."))

        # ------------------------------------------------ common name
        spec = self.spec("R6_COMMON_NAME")
        g = f("generic_name")
        if g.found and g.status == "DETECTED":
            how = {"label": "explicit label",
                   "commodity_term": f"product name containing the commodity term '{g.normalized.get('term', '')}' - verify"}.get(
                g.normalized.get("method"), "text matching the product name entered by the inspector")
            out.append(spec.result(PASS, f"Common/generic name '{g.value}' identified ({how}).", ctx.evidence("generic_name")))
        elif g.found:
            out.append(spec.result(NEEDS_VERIFICATION, f"Possible generic name '{g.value}' read with low confidence.",
                                   ctx.evidence("generic_name"), "Confirm the common name of the commodity on the package."))
        elif f("product_name") is not None and f("product_name").found:
            pn = f("product_name")
            out.append(spec.result(NEEDS_VERIFICATION,
                                   f"No labelled generic name; '{pn.value}' looks like the product name (identified from "
                                   f"print layout, not from a declaration label). Potential finding - verify.",
                                   ctx.evidence("product_name"), "Confirm that the common/generic name of the commodity is declared."))
        else:
            out.append(ctx.missing(spec, "The common or generic name of the commodity",
                                   "Declare the common/generic name of the commodity on the package."))

        # ------------------------------------------------ net quantity
        spec = self.spec("R6_NET_QUANTITY")
        q = f("net_quantity")
        if q.found and not q.normalized.get("unparsed") and q.status in ("DETECTED", "LOW_CONFIDENCE"):
            out.append(spec.result(PASS, f"Net quantity '{q.value}' declared.", ctx.evidence("net_quantity")))
        elif q.found:
            out.append(spec.result(NEEDS_VERIFICATION, "A net quantity declaration was located but could not be read reliably. "
                                   + (q.note or ""), ctx.evidence("net_quantity"), "Verify the net quantity declaration."))
        else:
            out.append(ctx.missing(spec, "The net quantity declaration",
                                   "Declare net quantity in standard units of weight, measure or number."))

        # ------------------------------------------------ MRP
        spec = self.spec("R6_MRP")
        p = f("mrp")
        if p.found:
            amount = p.normalized.get("amount")
            readings = {round(amount, 2)} | {round(a, 2) for a in p.normalized.get("amount_alternatives") or []}
            conflicts = []
            for alt in p.alternatives:
                alt_read = {round(alt["normalized"].get("amount", -1), 2)} | \
                           {round(a, 2) for a in alt["normalized"].get("amount_alternatives") or []}
                if not (alt_read & readings) and alt["confidence"] >= 60:
                    conflicts.append(alt)
            if amount is not None and amount <= 0:
                out.append(spec.result(NON_COMPLIANT, "Declared MRP is zero or invalid.", ctx.evidence("mrp"),
                                       "Declare a valid retail sale price."))
            elif conflicts:
                ev = ctx.evidence("mrp") + [{"field": "mrp", "label": "Conflicting MRP", "text": c["evidence"],
                                             "value": c["value"], "confidence": c["confidence"],
                                             "image_id": c["source_image_id"], "image": c["source_image"],
                                             "side": c["side"], "bbox": c["bbox"]} for c in conflicts]
                vals = ", ".join([p.value] + [c["value"] for c in conflicts])
                out.append(spec.result(NON_COMPLIANT,
                                       f"Contradictory MRP declarations on the same package: {vals}. A package must "
                                       f"carry a single retail sale price.", ev,
                                       "Remove the conflicting price declaration so that only one MRP appears."))
            elif p.status == "DETECTED":
                note = f" ({p.note})" if p.note else ""
                out.append(spec.result(PASS, f"MRP {p.value} declared{note}.", ctx.evidence("mrp")))
            else:
                out.append(spec.result(NEEDS_VERIFICATION,
                                       f"MRP read as {p.value} with low OCR confidence ({p.confidence:.0f}%).",
                                       ctx.evidence("mrp"), "Confirm the MRP amount on the package."))
        else:
            out.append(ctx.missing(spec, "The MRP declaration", "Declare the maximum retail price (MRP) in ₹."))

        # ------------------------------------------------ MRP inclusive of taxes
        spec = self.spec("R6_MRP_TAXES")
        if not p.found:
            out.append(spec.result(NEEDS_VERIFICATION, "Cannot evaluate: MRP declaration not extracted.",
                                   recommendation="Declare MRP as 'inclusive of all taxes'."))
        elif p.normalized.get("tax_exclusive_wording"):
            out.append(spec.result(NON_COMPLIANT, "The price declaration indicates taxes are charged over and above MRP "
                                   "(e.g. 'plus taxes'). MRP must be inclusive of all taxes.", ctx.evidence("mrp"),
                                   "Declare MRP as inclusive of all taxes and remove 'plus taxes' wording."))
        elif p.normalized.get("inclusive_of_taxes"):
            out.append(spec.result(PASS, "MRP is declared as inclusive of all taxes.", ctx.evidence("mrp")))
        else:
            out.append(ctx.missing(spec, "The statement 'inclusive of all taxes' next to the MRP",
                                   "Add 'Inclusive of all taxes' to the MRP declaration."))

        # ------------------------------------------------ month & year
        spec = self.spec("R6_DATE")
        d = f("mfg_date")
        insp = ctx.inspection_date
        if d.found and d.normalized.get("type") == "date":
            y, mth = d.normalized["year"], d.normalized["month"]
            if insp and (y, mth) > (insp.year, insp.month):
                out.append(spec.result(NON_COMPLIANT, f"Declared manufacture/packing date {mth:02d}/{y} is later than "
                                       f"the inspection date {insp:%m/%Y}.", ctx.evidence("mfg_date"),
                                       "Correct the month and year of manufacture/packing."))
            elif d.status == "DETECTED":
                out.append(spec.result(PASS, f"Month and year of manufacture/packing declared: {d.value}.",
                                       ctx.evidence("mfg_date")))
            else:
                out.append(spec.result(NEEDS_VERIFICATION, f"Date read as {d.value} with low confidence.",
                                       ctx.evidence("mfg_date"), "Confirm the month and year of manufacture/packing."))
        elif d.found:
            out.append(spec.result(NEEDS_VERIFICATION, d.note or "Date label found but value not readable.",
                                   ctx.evidence("mfg_date"), "Verify the month/year printed (often an ink-jet stamp).",
                                   verification="Read the ink-jet/embossed date on the physical package."))
        else:
            out.append(ctx.missing(spec, "The month and year of manufacture/packing/import",
                                   "Declare the month and year in which the commodity is manufactured, packed or imported."))

        # ------------------------------------------------ best before
        spec = self.spec("R6_BEST_BEFORE")
        b = f("best_before")
        if not ctx.category_cfg.get("best_before_required"):
            out.append(spec.result(NOT_APPLICABLE, f"Not required for the '{ctx.category_cfg['label']}' category configuration.",
                                   applicable=False))
        elif b.found and b.normalized.get("type") == "date" and d.found and d.normalized.get("type") == "date" and \
                (b.normalized["year"], b.normalized["month"]) < (d.normalized["year"], d.normalized["month"]):
            out.append(spec.result(NON_COMPLIANT, f"Best-before/expiry {b.value} is earlier than the manufacture/packing "
                                   f"date {d.value}.", ctx.evidence("best_before", "mfg_date"),
                                   "Correct the best-before / expiry declaration."))
        elif b.found and b.status in ("DETECTED",):
            out.append(spec.result(PASS, f"Best before / use by declared: {b.value}.", ctx.evidence("best_before")))
        elif b.found:
            out.append(spec.result(NEEDS_VERIFICATION, b.note or f"Best-before read as '{b.value}' with low confidence.",
                                   ctx.evidence("best_before"), "Verify the best-before / use-by declaration."))
        else:
            out.append(ctx.missing(spec, "The best before / use by date",
                                   "Declare the best-before or use-by date for this commodity."))

        # ------------------------------------------------ consumer care
        spec = self.spec("R6_CONSUMER_CARE")
        c = f("consumer_care")
        if c.found and (c.normalized.get("phones") or c.normalized.get("emails")) and c.status in ("DETECTED", "LOW_CONFIDENCE"):
            out.append(spec.result(PASS, f"Consumer-care details declared: {c.value}.", ctx.evidence("consumer_care")))
        elif c.found:
            out.append(spec.result(NEEDS_VERIFICATION, c.note or "Consumer-care details only partially readable.",
                                   ctx.evidence("consumer_care"), "Verify the consumer-care telephone number / e-mail."))
        else:
            out.append(ctx.missing(spec, "Consumer-care details (name/address/telephone/e-mail for complaints)",
                                   "Declare consumer-care details for complaints: telephone number and/or e-mail."))

        # ------------------------------------------------ country of origin
        spec = self.spec("R6_ORIGIN")
        o = f("country_of_origin")
        if not ctx.is_imported:
            if o.found:
                out.append(spec.result(NOT_APPLICABLE, f"Domestic product (origin declared: {o.value}); "
                                       f"mandatory only for imported packages.", ctx.evidence("country_of_origin"),
                                       applicable=False))
            else:
                out.append(spec.result(NOT_APPLICABLE, "Product not marked as imported by the inspector.", applicable=False))
        elif o.found and o.value.upper() == "INDIA":
            out.append(spec.result(NEEDS_VERIFICATION, "Product was marked as imported but the label declares India as the "
                                   "country of origin.", ctx.evidence("country_of_origin"),
                                   "Confirm the actual country of origin / manufacture."))
        elif o.found:
            out.append(spec.result(PASS, f"Country of origin declared: {o.value}.", ctx.evidence("country_of_origin")))
        else:
            out.append(ctx.missing(spec, "The country of origin", "Declare the country of origin for imported goods."))

        # ------------------------------------------------ unit sale price
        out.append(self._usp(ctx))
        return out

    def _usp(self, ctx: RuleContext):
        spec = self.spec("R6_USP")
        q, p, u = ctx.field("net_quantity"), ctx.field("mrp"), ctx.field("unit_sale_price")
        if not ctx.category_cfg.get("unit_sale_price_applicable"):
            return spec.result(NOT_APPLICABLE, f"Not configured as applicable for '{ctx.category_cfg['label']}'.",
                               applicable=False)
        if q.found and q.normalized.get("dimension") not in (None, "mass", "volume"):
            return spec.result(NOT_APPLICABLE, f"Net quantity is declared by {q.normalized.get('dimension')}; unit sale "
                               "price check is configured for weight/volume packages.", ctx.evidence("net_quantity"),
                               applicable=False)
        if not u.found or u.normalized.get("unparsed"):
            if u.found:
                return spec.result(NEEDS_VERIFICATION, u.note, ctx.evidence("unit_sale_price"),
                                   "Verify the unit sale price declaration.")
            return ctx.missing(spec, "The unit sale price", "Declare the unit sale price (e.g. ₹ per kg / per litre).")
        if not (q.found and p.found and q.normalized.get("base_value") and p.normalized.get("amount")):
            return spec.result(NEEDS_VERIFICATION, f"Unit sale price '{u.value}' found but MRP or net quantity is not "
                               f"available to verify the arithmetic.", ctx.evidence("unit_sale_price"))
        if q.normalized.get("dimension") != u.normalized.get("dimension"):
            return spec.result(NEEDS_VERIFICATION, f"Unit sale price is expressed per {u.normalized.get('unit_symbol')} "
                               f"but net quantity is in {q.normalized.get('unit_symbol')}.",
                               ctx.evidence("unit_sale_price", "net_quantity"))
        units = q.normalized["base_value"] / u.normalized["per_base"]
        expected = p.normalized["amount"] / units
        declared = u.normalized["amount"]
        tol = ctx.common["usp_tolerance"]
        diff = abs(expected - declared)
        ev = ctx.evidence("unit_sale_price", "mrp", "net_quantity")
        pq, sym = u.normalized["per_quantity"], u.normalized["unit_symbol"]
        per = sym if pq == 1 else f"{pq:g} {sym}"
        calc = (f"MRP ₹{p.normalized['amount']:,.2f} ÷ ({q.value} ÷ {u.normalized['per_quantity']:g} "
                f"{u.normalized['unit_symbol']}) = ₹{expected:,.2f} per {per}")
        # the absolute tolerance is meant for prices per kg / L; for a price per g / ml (e.g. ₹0.13 per g) a fixed
        # ₹0.50 would hide any error, so it is scaled to the unit (never below paise rounding)
        abs_tol = max(0.006, tol["absolute_rupees"] * min(1.0, u.normalized["per_base"] / 1000.0))
        if diff <= max(abs_tol, expected * tol["relative"]):
            return spec.result(PASS, f"Unit sale price ₹{declared:,.2f} per {per} is consistent: {calc}.", ev)
        alt_note = ""
        alts = u.normalized.get("amount_alternatives") or []
        if alts:
            alt_note = f" (alternative OCR reading ₹{alts[0]:,.2f} is also inconsistent)"
        if u.status != "DETECTED" or p.status != "DETECTED" or q.status != "DETECTED":
            return spec.result(NEEDS_VERIFICATION, f"Declared unit sale price ₹{declared:,.2f} per {per} does not match "
                               f"{calc}{alt_note}, but one of the values was read with low confidence.", ev,
                               "Verify MRP, net quantity and unit sale price on the package.")
        return spec.result(NON_COMPLIANT, f"Declared unit sale price ₹{declared:,.2f} per {per} is inconsistent with "
                           f"{calc}{alt_note}.", ev, "Correct the unit sale price so that it equals MRP ÷ net quantity.")
