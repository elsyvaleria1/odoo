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

# EPC URI schemes: what each decodes to, and the one URI type it is written
# under -- `urn:epc:<type>:<scheme>`. A `tag` encoding prefixes the data with
# a filter value.
URI_SCHEMES = {
    "lgtin": ("gtin", "class"),
    "sgtin": ("gtin", "id"),
    "sgtin-96": ("gtin", "tag"),
    "sgtin-198": ("gtin", "tag"),
    "sscc": ("sscc", "id"),
    "sscc-96": ("sscc", "tag"),
}
# The company prefix and the reference that follows it together fill every
# digit of a GTIN-14 or an SSCC but the check digit.
URI_DATA_FIELDS = {"gtin": 3, "sscc": 2}
URI_KEY_DIGITS = {"gtin": 13, "sscc": 17}

_ASCII_DIGITS = re.compile(r"\A[0-9]+\Z")

# `_match_pattern` runs a user-authored regex on every scan. Patterns are
# validated against catastrophic backtracking on write (`barcode.rule.
# _check_pattern`), but the subject is capped as well so that a pattern which
# slips through cannot turn one scan into unbounded CPU.
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
        """Returns a valid zero padded EAN-13 from an EAN prefix.

        :type ean: str
        """
        ean = ean[0:13].zfill(13)
        return ean[0:-1] + str(get_barcode_check_digit(ean))

    def _normalize_upc(self, upc):
        """Returns a valid zero padded UPC-A from a UPC-A prefix.

        :type upc: str
        """
        return self._normalize_ean("0" + upc)[1:]

    def _match_pattern(self, barcode, pattern):
        """Checks barcode matches the pattern and retrieves the optional numeric value in barcode.

        :param barcode:
        :type barcode: str
        :param pattern:
        :type pattern: str
        :return: an object containing:
            - value: the numerical value encoded in the barcode (0 if no value encoded)
            - base_code: the barcode in which numerical content is replaced by 0's
            - match: boolean
        :rtype: dict
        """
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
        # an optional or alternated value group can match without taking part
        digits = found.group("value") if whole_size is not None else None
        if digits is None:
            return match
        whole, decimal = digits[:whole_size], digits[whole_size:]
        match["value"] = float(f"{whole or 0}.{decimal or 0}")
        start, end = found.span("value")
        match["base_code"] = barcode[:start] + "0" * len(digits) + barcode[end:]
        return match

    def parse_barcode(self, barcode):
        """Parse a scanned barcode against this nomenclature.

        :param barcode:
        :type barcode: str
        :return: for an EPC URI, the list of data dicts it decodes to;
            otherwise a single dict, see :meth:`parse_nomenclature_barcode`.
        :rtype: dict | list[dict]
        """
        if len(self) > 1:
            raise ValueError(
                f"parse_barcode expects a single nomenclature, got {len(self)}"
            )
        if barcode.startswith("urn:"):
            return self._parse_uri(barcode)
        return self.parse_nomenclature_barcode(barcode)

    def parse_nomenclature_barcode(self, barcode):
        """Attempts to interpret and parse a barcode.

        :param barcode:
        :type barcode: str
        :return: A object containing various information about the barcode, like as:

            - code: the barcode
            - type: the barcode's type
            - value: if the id encodes a numerical value, it will be put there
            - base_code: the barcode code with all the encoding parts set to
              zero; the one put on the product in the backend

        :rtype: dict
        """
        # An `alias` rule restates the scan as another barcode, which must then
        # be parsed from the first rule again -- resuming at the next rule would
        # make the outcome depend on the alias rule's own sequence. `seen`
        # stops a cycle of aliases from looping forever.
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
        """Match `barcode` against this nomenclature's rules, once.

        Returns the same dict as :meth:`parse_nomenclature_barcode`, except that
        a matched ``alias`` rule yields ``type == "alias"`` with ``code`` set to
        the aliased barcode, for the caller to resolve.
        """
        parsed_result = {
            "encoding": "",
            "type": "error",
            "code": barcode,
            "base_code": barcode,
            "value": 0,
        }

        # A UPC-A restated as EAN-13 always gains a leading zero, and
        # `is_barcode_encoding_valid` reads a leading zero as "this is really a
        # UPC-A". So the converted code can never validate as EAN-13: the
        # conversion has to stand in for the encoding check, not precede it.
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

    # RFID/URI stuff.
    @api.model
    def _parse_uri(self, barcode):
        """Convert supported URI format (lgtin, sgtin, sgtin-96, sgtin-198,
        sscc and sscc-96) into a GS1 barcode.

        Every branch returns a list of data dicts -- callers rely on that shape
        (``len()``, ``[0]["type"]``, ...). A URI this method cannot decode is a
        failed parse, reported as an empty list rather than a raised exception:
        the argument is scanned input, so a malformed one is expected traffic.

        :param str barcode: the URI as a string.
        :rtype: list[dict]
        """
        parts = [part.strip() for part in barcode.split(":")]
        # urn:<namespace>:<type>:<identifier>:<data>
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
        # Only the two leading fields feed the check-digit computation; an
        # SGTIN-198 serial is legitimately alphanumeric and is passed through.
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
        """Refuse to delete a nomenclature a company is still scanning with.

        `res.company.barcodes_config_id.nomenclature_id` is a plain Many2one, so the default
        `ondelete="set null"` used to empty it silently. Nothing raised, and
        nothing pointed at the deletion: every subsequent scan simply parsed
        against no rules and came back `type: "error"`.
        """
        # Through the configuration rows, not `res.company`: an archived
        # company is still configured, and would lose its nomenclature.
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
