import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.barcode import (
    get_barcode_check_digit,
    gs1_check_digit,
    is_barcode_encoding_valid,
)

from .barcode_rule import RULE_REGEX_FLAGS, rule_regex

_logger = logging.getLogger(__name__)


UPC_EAN_CONVERSIONS = [
    ("none", "Never"),
    ("ean2upc", "EAN-13 to UPC-A"),
    ("upc2ean", "UPC-A to EAN-13"),
    ("always", "Always"),
]

URI_SCHEMES = {
    "lgtin": ("gtin", "class"),
    "sgtin": ("gtin", "id"),
    "sgtin-96": ("gtin", "tag"),
    "sgtin-198": ("gtin", "tag"),
    "sscc": ("sscc", "id"),
    "sscc-96": ("sscc", "tag"),
}
URI_DATA_FIELDS = {"gtin": 3, "sscc": 2}
URI_KEY_DIGITS = {"gtin": 13, "sscc": 17}

_ASCII_DIGITS = re.compile(r"\A[0-9]+\Z")

MAX_BARCODE_LENGTH = 256


class BarcodeNomenclature(models.Model):
    _name = "barcode.nomenclature"
    _description = "Barcode Nomenclature"

    name = fields.Char(
        string="Barcode Nomenclature",
        required=True,
        help="An internal identification of the barcode nomenclature",
    )
    rule_ids = fields.One2many(
        comodel_name="barcode.rule",
        inverse_name="barcode_nomenclature_id",
        string="Rules",
        help="The list of barcode rules",
    )
    upc_ean_conv = fields.Selection(
        selection=UPC_EAN_CONVERSIONS,
        string="UPC/EAN Conversion",
        default="always",
        required=True,
        help="UPC Codes can be converted to EAN by prefixing them with a zero. This setting determines if a UPC/EAN barcode should be automatically converted in one way or another when trying to match a rule with the other encoding.",
    )

    def _normalize_ean(self, ean):
        ean = ean[0:13].zfill(13)
        return ean[0:-1] + str(get_barcode_check_digit(ean))

    def _normalize_upc(self, upc):
        return self._normalize_ean("0" + upc)[1:]

    def _match_pattern(self, barcode, pattern):
        match = {
            "value": 0,
            "base_code": barcode,
            "match": False,
        }
        if len(barcode) > MAX_BARCODE_LENGTH:
            return match
        regex, whole_size = rule_regex(pattern)
        found = re.match(regex, barcode, RULE_REGEX_FLAGS)
        if not found:
            return match
        match["match"] = True
        digits = found.group("value") if whole_size is not None else None
        if digits is None:
            return match
        whole, decimal = digits[:whole_size], digits[whole_size:]
        match["value"] = float(f"{whole or 0}.{decimal or 0}")
        start, end = found.span("value")
        match["base_code"] = barcode[:start] + "0" * len(digits) + barcode[end:]
        return match

    def parse_barcode(self, barcode):
        if len(self) > 1:
            raise ValueError(
                f"parse_barcode expects a single nomenclature, got {len(self)}"
            )
        if barcode.startswith("urn:"):
            return self._parse_uri(barcode)
        return self.parse_nomenclature_barcode(barcode)

    def parse_nomenclature_barcode(self, barcode):
        seen = set()
        while True:
            parsed_result = self._match_rules(barcode)
            if parsed_result["type"] != "alias":
                return parsed_result
            seen.add(barcode)
            barcode = parsed_result["code"]
            if barcode in seen:
                _logger.warning(
                    "Barcode nomenclature %r: alias cycle on %r, giving up.",
                    self.display_name,
                    barcode,
                )
                parsed_result["type"] = "error"
                return parsed_result

    def _match_rules(self, barcode):
        parsed_result = {
            "encoding": "",
            "type": "error",
            "code": barcode,
            "base_code": barcode,
            "value": 0,
        }

        as_ean13 = (
            "0" + barcode
            if self.upc_ean_conv in ("upc2ean", "always")
            and is_barcode_encoding_valid(barcode, "upca")
            else None
        )
        as_upca = (
            barcode[1:]
            if self.upc_ean_conv in ("ean2upc", "always")
            and barcode[:1] == "0"
            and is_barcode_encoding_valid(barcode[1:], "upca")
            else None
        )
        for rule in self.rule_ids:
            if rule.encoding == "ean13" and as_ean13:
                cur_barcode = as_ean13
            elif rule.encoding == "upca" and as_upca:
                cur_barcode = as_upca
            elif is_barcode_encoding_valid(barcode, rule.encoding):
                cur_barcode = barcode
            else:
                continue

            match = self._match_pattern(cur_barcode, rule.pattern)
            if not match["match"]:
                continue

            if rule.type == "alias":
                parsed_result["type"] = "alias"
                parsed_result["code"] = rule.alias
                return parsed_result

            parsed_result["encoding"] = rule.encoding
            parsed_result["type"] = rule.type
            parsed_result["value"] = match["value"]
            parsed_result["code"] = cur_barcode
            if rule.encoding == "ean13":
                parsed_result["base_code"] = self._normalize_ean(match["base_code"])
            elif rule.encoding == "upca":
                parsed_result["base_code"] = self._normalize_upc(match["base_code"])
            else:
                parsed_result["base_code"] = match["base_code"]
            return parsed_result

        return parsed_result

    @api.model
    def _parse_uri(self, barcode):
        parts = [part.strip() for part in barcode.split(":")]
        if len(parts) != 5:
            _logger.info(
                "Malformed EPC URI %r: expected 5 ':'-separated parts.", barcode
            )
            return []
        namespace, uri_type, identifier = parts[1:4]
        data = parts[4].split(".")

        scheme = URI_SCHEMES.get(identifier)
        if scheme is None or namespace != "epc" or uri_type != scheme[1]:
            _logger.info("Unrecognized EPC URI %r", barcode)
            return []
        key, uri_type = scheme
        filtered = uri_type == "tag"
        expected = URI_DATA_FIELDS[key] + filtered
        if len(data) != expected:
            _logger.info(
                "Malformed EPC URI %r: %r expects %d '.'-separated fields, got %d.",
                barcode,
                identifier,
                expected,
                len(data),
            )
            return []
        if filtered:
            data = data[1:]
        company_prefix, reference = data[:2]
        if not (
            _ASCII_DIGITS.match(company_prefix)
            and _ASCII_DIGITS.match(reference)
            and len(company_prefix) + len(reference) == URI_KEY_DIGITS[key]
        ):
            _logger.info(
                "Malformed EPC URI %r: company prefix and reference must be %d digits together.",
                barcode,
                URI_KEY_DIGITS[key],
            )
            return []

        if key == "sscc":
            return self._convert_uri_sscc_data_into_package(barcode, data)
        return self._convert_uri_gtin_data_into_tracking_number(barcode, data)

    @api.model
    def _convert_uri_gtin_data_into_tracking_number(self, base_code, data) -> list:
        gs1_company_prefix, item_ref_and_indicator, tracking_number = data
        indicator = item_ref_and_indicator[0]
        item_ref = item_ref_and_indicator[1:]
        product_barcode = indicator + gs1_company_prefix + item_ref
        product_barcode += str(gs1_check_digit(product_barcode))
        return [
            {
                "base_code": base_code,
                "code": product_barcode,
                "encoding": "",
                "type": "product",
                "value": product_barcode,
            },
            {
                "base_code": base_code,
                "code": tracking_number,
                "encoding": "",
                "type": "lot",
                "value": tracking_number,
            },
        ]

    @api.model
    def _convert_uri_sscc_data_into_package(self, base_code, data) -> list:
        gs1_company_prefix, serial_reference = data
        extension = serial_reference[0]
        serial_ref = serial_reference[1:]
        sscc = extension + gs1_company_prefix + serial_ref
        sscc += str(gs1_check_digit(sscc))
        return [
            {
                "base_code": base_code,
                "code": sscc,
                "encoding": "",
                "type": "package",
                "value": sscc,
            }
        ]

    @api.ondelete(at_uninstall=False)
    def _unlink_except_default(self) -> None:
        default_record = self.env.ref(
            "barcodes.default_barcode_nomenclature", raise_if_not_found=False
        )
        if default_record and default_record in self:
            raise UserError(
                self.env._(
                    "You cannot delete '%(name)s' because it's the default barcode nomenclature.",
                    name=default_record.display_name,
                )
            )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used_by_company(self) -> None:
        configs = (
            self.env["barcodes.config"]
            .sudo()
            .search([("nomenclature_id", "in", self.ids)])
        )
        companies = configs.company_id
        if companies:
            raise UserError(
                self.env._(
                    "You cannot delete the barcode nomenclature %(names)s because "
                    "it is still used by: %(companies)s.",
                    names=", ".join(configs.nomenclature_id.mapped("display_name")),
                    companies=", ".join(companies.mapped("display_name")),
                )
            )
