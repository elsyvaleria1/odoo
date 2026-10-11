import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

SDD_CREDITOR_IDENTIFIER_REGEX_PATTERN = r"(?P<country_code>[A-Z]{2})(?P<check_digits>\d{2})(?P<business_code>.{3})(?P<country_identifier>.{1,28})"


class ResCompany(models.Model):
    _inherit = "res.company"

    sdd_creditor_identifier = fields.Char(
        string="SDD creditor identifier",
        help="SEPA Direct Debit creditor identifier of the company, given by the bank.",
    )

    @api.constrains("sdd_creditor_identifier")
    def check_sdd_creditor_identifier(self) -> None:
        for record in self:
            if (
                not record.sdd_creditor_identifier
            ):
                continue

            if len(record.sdd_creditor_identifier) > 35:
                raise ValidationError(
                    self.env._(
                        "The creditor identifier exceeds the maximum length of 35 characters."
                    )
                )

            matcher = re.match(
                SDD_CREDITOR_IDENTIFIER_REGEX_PATTERN,
                record.sdd_creditor_identifier.upper(),
            )
            if matcher:
                country_code = matcher.group("country_code")
                check_digits = matcher.group("check_digits")
                country_identifier = matcher.group("country_identifier")

                test_str = (
                    re.sub(r"[^A-Z0-9]", "", country_identifier) + country_code + "00"
                )
                converted_test_str = self._convert_sdd_test_str(test_str)

                if (98 - int(converted_test_str) % 97) != int(
                    check_digits
                ):
                    raise ValidationError(
                        self.env._(
                            "Invalid creditor identifier. Make sure you made no typo."
                        )
                    )
            else:
                raise ValidationError(
                    self.env._("Invalid creditor identifier. Wrong format.")
                )

    @api.model
    def _convert_sdd_test_str(self, test_str):
        ascii_value_shift = 55
        rslt = ""
        for char in test_str:
            if re.match(r"[A-Z]", char):
                rslt += str(ord(char) - ascii_value_shift)
            else:
                rslt += char
        return rslt
