import calendar
import datetime
import functools
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.barcode import get_barcode_check_digit
from odoo.libs.debug_log import DebugLog

from odoo.addons.barcodes.models.barcode_rule import (
    RULE_REGEX_FLAGS,
    browser_semantics,
    unportable_construct,
)

FNC1_CHAR = "\x1d"
# What a camera scanner prefixes a GS1 read with to name its symbology.
SYMBOLOGY_IDENTIFIERS = ("]C1", "]e0", "]d2", "]Q3", "]J1")
_ASCII_DIGITS = re.compile(r"\A[0-9]+\Z")

_debug = DebugLog(__name__)


@functools.lru_cache(maxsize=1024)
def _gs1_element_regex(pattern, separator_group):
    return re.compile(
        "^" + browser_semantics(pattern) + separator_group, RULE_REGEX_FLAGS
    )


# The zero-padded lengths a stored GTIN or SSCC can carry: EAN-8, UPC-A,
# EAN-13, GTIN-14 and SSCC.
PADDED_KEY_LENGTHS = (8, 12, 13, 14, 18)


def _unpadded_condition(field, operator, digits):
    """Match `digits` whatever zero padding the stored barcode carries.

    An exact operator stays exact: an `ilike` on the digits would also match
    every barcode that merely contains them, and a caller taking the first
    result would act on another product.
    """
    if operator in ("ilike", "not ilike"):
        return Domain(field, operator, digits)
    candidates = [digits] + [
        digits.rjust(length, "0")
        for length in PADDED_KEY_LENGTHS
        if length > len(digits)
    ]
    return Domain(field, "in" if operator == "=" else "not in", candidates)


class BarcodeNomenclature(models.Model):
    _inherit = "barcode.nomenclature"

    is_gs1_nomenclature = fields.Boolean(
        string="Is GS1 Nomenclature",
        help="This Nomenclature use the GS1 specification, only GS1-128 encoding rules is accepted is this kind of nomenclature.",
    )
    gs1_separator_fnc1 = fields.Char(
        string="FNC1 Separator",
        trim=False,
        default=r"(Alt029|#|\x1D)",
        help="Alternative regex delimiter for the FNC1. The separator must not match the begin/end of any related rules pattern.",
    )

    @api.constrains("gs1_separator_fnc1")
    def _check_gs1_separator_fnc1(self) -> None:
        for nom in self:
            if nom.is_gs1_nomenclature and nom.gs1_separator_fnc1:
                try:
                    re.compile(nom._gs1_separator_group(), RULE_REGEX_FLAGS)
                except re.error as error:
                    raise ValidationError(
                        self.env._(
                            "The FNC1 Separator Alternative is not a valid Regex: %(error)s",
                            error=error,
                        )
                    ) from error
                # the barcode service rewrites scanned separators in the browser
                if construct := unportable_construct(nom.gs1_separator_fnc1):
                    raise ValidationError(
                        self.env._(
                            "The FNC1 separator %(separator)s uses %(construct)s, which the browser does not read as the server does.",
                            separator=nom.gs1_separator_fnc1,
                            construct=construct,
                        )
                    )

    def _gs1_separator_group(self):
        if not self.gs1_separator_fnc1:
            return FNC1_CHAR + "*"
        return f"(?:{browser_semantics(self.gs1_separator_fnc1)})*"

    @api.model
    def gs1_date_to_date(self, gs1_date):
        """Converts a GS1 date into a datetime.date.

        :param gs1_date: A date formatted as yymmdd
        :type gs1_date: str
        :return: converted date
        :rtype: datetime.date
        """
        # See 7.12 Determination of century in dates:
        # https://www.gs1.org/sites/default/files/docs/barcodes/GS1_General_Specifications.pdf
        now = datetime.date.today()
        current_century = now.year // 100
        substract_year = int(gs1_date[0:2]) - (now.year % 100)
        century = (
            (51 <= substract_year <= 99 and current_century - 1)
            or (-99 <= substract_year <= -50 and current_century + 1)
            or current_century
        )
        year = century * 100 + int(gs1_date[0:2])

        try:
            if (
                gs1_date[-2:] == "00"
            ):  # Day is not mandatory, when not set -> last day of the month
                date = datetime.datetime.strptime(str(year) + gs1_date[2:4], "%Y%m")
                date = date.replace(
                    day=calendar.monthrange(year, int(gs1_date[2:4]))[1]
                )
            else:
                date = datetime.datetime.strptime(str(year) + gs1_date[2:], "%Y%m%d")
        except (ValueError, calendar.IllegalMonthError) as e:
            raise ValidationError(
                self.env._(
                    "A GS1 barcode nomenclature pattern was matched. However, the barcode failed to be converted to a valid date: '%(error_message)s'",
                    error_message=e,
                )
            ) from e
        return date.date()

    def parse_gs1_rule_pattern(self, match, rule) -> dict | None:
        """Read a matched GS1 element as its rule's content type.

        Content the type cannot hold -- a measure or identifier that is not
        digits, a date that is not on the calendar, a wrong check digit -- is
        not this rule: None, so decomposition tries the next one. Raising here
        failed a scan with a configuration error, and the browser read the
        same element as NaN or a rolled-over date.
        """
        ai, raw = match.group(1), match.group(2)
        value, rejection = self._gs1_element_value(rule, ai, raw)
        if rejection:
            _debug.logic(
                "gs1.element_rejected", rule=rule.id, value=raw, reason=rejection
            )
            return None
        return {
            "rule": rule,
            "type": rule.type,
            "ai": ai,
            "string_value": raw,
            "value": value,
        }

    def _gs1_element_value(self, rule, ai, raw) -> tuple:
        content_type = rule.gs1_content_type
        if content_type == "alpha" or not content_type:
            return raw, None
        if not _ASCII_DIGITS.match(raw):
            return None, "not digits"
        if content_type == "measure":
            decimals = 0
            if rule.gs1_decimal_usage:
                if not _ASCII_DIGITS.match(ai[-1:]):
                    return None, "no decimal digit in the AI"
                decimals = int(ai[-1])
            if decimals > len(raw):
                return None, "more decimals than digits"
            if not decimals:
                return int(raw), None
            whole, fraction = raw[: len(raw) - decimals], raw[len(raw) - decimals :]
            return float(f"{whole or 0}.{fraction}"), None
        if content_type == "identifier":
            if raw[-1] != str(get_barcode_check_digit(raw)):
                return None, "check digit"
            return raw, None
        if len(raw) != 6:
            return None, "not yymmdd"
        try:
            return self.gs1_date_to_date(raw), None
        except ValidationError:
            return None, "not a calendar date"

    def gs1_decompose_extended(self, barcode):
        """Decompose a GS1 element string into its elements, in order.

        Each element is matched from the first rule again, by sequence, and a
        run of separators ends a variable-length element. Returns None when
        some part of the barcode is read by no rule.
        """
        self.check_singleton()
        separator_group = self._gs1_separator_group()
        # a camera scanner's symbology identifier, then any leading FNC1
        for identifier in SYMBOLOGY_IDENTIFIERS:
            if barcode.startswith(identifier):
                barcode = barcode[len(identifier) :]
                break
        barcode = barcode.lstrip(FNC1_CHAR)
        gs1_rules = self.rule_ids.filtered(lambda r: r.encoding == "gs1-128")
        regexes = [
            (rule, _gs1_element_regex(rule.pattern, separator_group))
            for rule in gs1_rules
        ]

        def next_element(remaining):
            # at least two groups: the AI, then the value (named groups
            # differ between Python and the browser, so they go unused)
            for rule, regex in regexes:
                match = regex.match(remaining)
                if match and len(match.groups()) >= 2:
                    element = self.parse_gs1_rule_pattern(match, rule)
                    if element:
                        return element, match.end()
            return None, 0

        results = []
        while barcode:
            element, consumed = next_element(barcode)
            if not consumed:
                _debug.logic("gs1.undecomposable", rest=barcode, found=len(results))
                return None
            results.append(element)
            barcode = barcode[consumed:]
        return results

    def parse_nomenclature_barcode(self, barcode):
        if self.is_gs1_nomenclature:
            return self.gs1_decompose_extended(barcode)
        return super().parse_nomenclature_barcode(barcode)

    @api.model
    def _preprocess_gs1_search_args(self, domain, barcode_types, field="barcode"):
        """Preprocess `domain` in `_search` to support searching with a GS1 barcode.

        Strip the GS1 padding when searching on `barcode`, keeping only the
        significant digits of the parsed value.
        """
        domain = Domain(domain)
        nomenclature = self.env.company.sudo().barcodes_config_id.nomenclature_id
        if not self.env.context.get("skip_preprocess_gs1"):

            def map_gs1_barcode(condition):
                if (
                    condition.field_expr != field
                    or not nomenclature.is_gs1_nomenclature
                ):
                    return condition
                # Check operator
                # handle `in` first and check the rest
                operator = condition.operator
                value = condition.value
                if not value:
                    return condition

                if operator in ("in", "not in") and len(value) > 1:
                    sub_domain = Domain.OR(
                        map_gs1_barcode(Domain(field, "=", v)) for v in value
                    )
                    if operator == "not in":
                        sub_domain = ~sub_domain
                    return sub_domain
                if operator in ("in", "not in"):
                    operator = "=" if operator == "in" else "!="
                    value = next(iter(value))
                elif operator not in ("ilike", "not ilike", "=", "!="):
                    return condition

                # a number is the ORM's to compare, as for any Char field
                if not value or not isinstance(value, str):
                    return condition
                parsed_data = nomenclature.parse_barcode(value) or []

                for data in parsed_data:
                    data_type = data["type"]
                    value = data["value"]
                    if data_type in barcode_types:
                        if data_type == "lot":
                            return Domain(field, operator, value)
                        match = re.match(r"0*([0-9]+)$", str(value))
                        if match:
                            unpadded_barcode = match.groups()[0]
                            return _unpadded_condition(
                                field, operator, unpadded_barcode
                            )
                        break

                # The barcode isn't a valid GS1 barcode, checks if it can be unpadded.
                if not parsed_data:
                    match = re.match(r"0+([0-9]+)$", value)
                    if match:
                        return _unpadded_condition(field, operator, match.groups()[0])
                return condition

            domain = domain.map_conditions(map_gs1_barcode)
        return domain
