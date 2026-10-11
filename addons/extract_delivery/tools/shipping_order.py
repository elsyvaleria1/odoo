from __future__ import annotations

import re
from typing import Any

from odoo.addons.extract.tools import (
    CHEAP,
    BaseExtractor,
    FieldSpec,
    Rule,
    register_extractor,
    register_schema,
)

DOC_TYPE = "shipping_order"
_MONEY_RE = re.compile(r"^\$?\s*(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2})$")
_DATE_RE = re.compile(r"FECHA\s+(?:EXP|DOC)\.?\s*(\d{2})[-/](\d{2})[-/](\d{4})")
_ORIGIN_RE = re.compile(r"^\s*ORIGEN:\s*(.+?)\s*$", re.MULTILINE)
_DESTINATION_RE = re.compile(r"^\s*DESTINO:\s*(.+?)\s*$", re.MULTILINE)


def _totals_hold(values: dict[str, Any]) -> bool:
    withheld = values.get("tax_withheld") or 0.0
    return (
        abs(values["subtotal"] + values["tax_amount"] - withheld - values["total"]) <= 1
    )


register_schema(
    DOC_TYPE,
    fields={
        "tracking_ref": FieldSpec(
            "str",
            required=True,
            help="The carrier's tracking number of the shipment (guía, talón)",
        ),
        "carrier_vat": FieldSpec("str", help="Tax identifier of the carrier"),
        "shipper_name": FieldSpec("str", help="Who sends the shipment (remitente)"),
        "consignee_name": FieldSpec("str", help="Who receives it (destinatario)"),
        "origin": FieldSpec("str", help="Origin branch or city"),
        "destination": FieldSpec("str", help="Destination city"),
        "service": FieldSpec(
            "str",
            help="ocurre: picked up at the carrier's branch; home: delivered to the address",
            choices=("ocurre", "home"),
        ),
        "date": FieldSpec("date", help="Date of the shipping order"),
        "subtotal": FieldSpec("float"),
        "tax_amount": FieldSpec("float", help="VAT charged"),
        "tax_withheld": FieldSpec("float", help="VAT withheld (IVA retenido)"),
        "total": FieldSpec(
            "float", required=True, help="Amount to pay, taxes included"
        ),
    },
    rules=[
        Rule(
            "shipping_totals",
            ("subtotal", "tax_amount", "total"),
            _totals_hold,
            "Subtotal plus VAT minus VAT withheld should give the total.",
        )
    ],
    instructions=(
        "A parcel carrier's shipping order (in Mexico: orden de servicio, talón, "
        "guía). The tracking number is printed under its barcode. The shipper "
        "(remitente) sends, the consignee (destinatario) receives. The total is "
        "what the shipment costs, taxes included."
    ),
)


def _tracking_patterns(env) -> list[re.Pattern]:
    if env is None:
        return []
    carriers = env["delivery.carrier"].search([("tracking_ref_pattern", "!=", False)])
    return [re.compile(pattern) for pattern in carriers.mapped("tracking_ref_pattern")]


def _amount(line: str) -> float | None:
    match = _MONEY_RE.match(line.strip())
    if not match:
        return None
    return float(f"{match.group(1).replace(',', '')}.{match.group(2)}")


def find_totals(text: str) -> dict[str, float]:
    lines = [line.strip() for line in (text or "").splitlines()]
    total = None
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].upper() == "TOTAL":
            total = next(
                (
                    value
                    for value in map(_amount, lines[index + 1 :])
                    if value is not None
                ),
                None,
            )
            figures = [
                value for value in map(_amount, lines[:index]) if value is not None
            ]
            break
    if total is None:
        return {}
    found = {"total": total}
    for start in range(len(figures) - 2, -1, -1):
        subtotal, tax, *rest = figures[start : start + 3]
        withheld = rest[0] if rest else 0.0
        if abs(subtotal + tax - withheld - total) <= 1:
            found.update(subtotal=subtotal, tax_amount=tax, tax_withheld=withheld)
            break
    return found


class ShippingOrderBarcode(BaseExtractor):
    """The tracking number from the sheet's barcode, when a configured carrier's
    pattern recognises it."""

    name = "shipping_order_barcode"
    doc_types = (DOC_TYPE,)
    needs = ("barcodes",)
    cost = CHEAP
    confidence = 0.95

    def extract(self, source, doc_type, wanted, env=None) -> dict[str, Any] | None:
        patterns = _tracking_patterns(env)
        for code in source.barcodes:
            code = code.strip().upper()
            if any(pattern.fullmatch(code) for pattern in patterns):
                return {"tracking_ref": code}
        return None


class ShippingOrderText(BaseExtractor):
    """Route, service, date and amounts from the sheet's text, and the tracking
    number when the barcode could not be read."""

    name = "shipping_order_text"
    doc_types = (DOC_TYPE,)
    needs = ("text",)
    cost = CHEAP
    confidence = 0.7

    def extract(self, source, doc_type, wanted, env=None) -> dict[str, Any] | None:
        text = source.text or ""
        upper = text.upper()
        found: dict[str, Any] = {}
        for pattern in _tracking_patterns(env):
            match = re.search(rf"(?<![A-Z0-9])(?:{pattern.pattern})(?![A-Z0-9])", upper)
            if match:
                found["tracking_ref"] = match.group(0)
                break
        if origin := _ORIGIN_RE.search(upper):
            found["origin"] = origin.group(1)
        if destination := _DESTINATION_RE.search(upper):
            found["destination"] = destination.group(1)
        if "OCURRE" in upper:
            found["service"] = "ocurre"
        elif "DOMICILIO" in upper:
            found["service"] = "home"
        if date := _DATE_RE.search(upper):
            day, month, year = date.groups()
            found["date"] = f"{year}-{month}-{day}"
        found.update(find_totals(text))
        return found or None


register_extractor(ShippingOrderBarcode())
register_extractor(ShippingOrderText())
