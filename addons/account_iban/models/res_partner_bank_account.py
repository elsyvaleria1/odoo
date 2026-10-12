import re
from typing import Literal

from odoo import api, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import LazyTranslate

_lt = LazyTranslate(__name__)


def normalize_iban(iban):
    return re.sub(r"[\W_]", "", iban or "")


def pretty_iban(iban):
    iban = normalize_iban(iban)
    try:
        check_iban(iban)
        iban = " ".join([iban[i : i + 4] for i in range(0, len(iban), 4)])
    except ValidationError:
        pass
    return iban


def get_bban_from_iban(iban):
    return normalize_iban(iban)[4:]


def get_iban_part(iban, number_kind) -> str | Literal[False]:
    iban_part_map = {
        "bank": "B",
        "branch": "S",
        "account": "C",
        "check": "k",
        "check_national": "K",
        "account_type": "T",
        "balance_account": "A",
        "fiscal_code": "F",
        "reserved": "R",
    }
    if not (mask_char := iban_part_map.get(number_kind.lower())):
        return False

    iban = normalize_iban(iban)
    country_code = iban[:2].lower()

    iban_nocc = iban[2:]
    template_nocc = _map_iban_template.get(country_code, "").replace(" ", "")[2:]
    if not template_nocc:
        return False

    return "".join(
        c for c, t in zip(iban_nocc, template_nocc, strict=False) if t == mask_char
    )


def check_iban(iban) -> None:
    iban = normalize_iban(iban)
    if not iban:
        raise ValidationError(_lt("There is no IBAN code."))

    country_code = iban[:2].lower()
    if country_code not in _map_iban_template:
        raise ValidationError(
            _lt("The IBAN is invalid, it should begin with the country code")
        )

    iban_template = _map_iban_template[country_code]
    if len(iban) != len(iban_template.replace(" ", "")) or not re.fullmatch(
        r"[a-zA-Z0-9]+", iban
    ):
        raise ValidationError(
            _lt(
                "The IBAN does not seem to be correct. You should have entered something like this %s\n"
                "Where B = National bank code, S = Branch code, C = Account No, k = Check digit",
                iban_template,
            )
        )

    check_chars = iban[4:] + iban[:4]
    digits = int("".join(str(int(char, 36)) for char in check_chars))
    if digits % 97 != 1:
        raise ValidationError(
            _lt("This IBAN does not pass the validation check, please verify it.")
        )


class ResPartnerBankAccount(models.Model):
    _inherit = "res.partner.bank.account"

    @api.model
    def _get_account_types_supported(self):
        rslt = super()._get_account_types_supported()
        rslt.append(("iban", self.env._("IBAN")))
        return rslt

    @api.model
    def _get_acc_type(self, acc_number):
        try:
            check_iban(acc_number)
            return "iban"
        except ValidationError:
            return super()._get_acc_type(acc_number)

    def get_bban(self):
        if self.acc_type != "iban":
            raise UserError(
                self.env._(
                    "Cannot compute the BBAN because the account number is not an IBAN."
                )
            )
        return get_bban_from_iban(self.acc_number)

    @api.model
    def _normalize_iban_acc_number(self, vals):
        if not vals.get("acc_number"):
            return vals
        vals = dict(vals)
        try:
            check_iban(vals["acc_number"])
            vals["acc_number"] = pretty_iban(vals["acc_number"])
        except ValidationError:
            pass
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_iban_acc_number(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._normalize_iban_acc_number(vals)
        return super().write(vals)

    @api.constrains("acc_number")
    def _check_iban(self) -> None:
        for bank in self:
            if bank.acc_type == "iban":
                check_iban(bank.acc_number)

    def is_valid_iban(self, iban="") -> bool:
        try:
            check_iban(iban)
            return True
        except ValidationError:
            return False


_map_iban_template = {
    "ad": "ADkk BBBB SSSS CCCC CCCC CCCC",
    "ae": "AEkk BBBC CCCC CCCC CCCC CCC",
    "al": "ALkk BBBS SSSK CCCC CCCC CCCC CCCC",
    "at": "ATkk BBBB BCCC CCCC CCCC",
    "az": "AZkk BBBB CCCC CCCC CCCC CCCC CCCC",
    "ba": "BAkk BBBS SSCC CCCC CCKK",
    "be": "BEkk BBBC CCCC CCKK",
    "bg": "BGkk BBBB SSSS TTCC CCCC CC",
    "bh": "BHkk BBBB CCCC CCCC CCCC CC",
    "br": "BRkk BBBB BBBB SSSS SCCC CCCC CCCT N",
    "by": "BYkk BBBB AAAA CCCC CCCC CCCC CCCC",
    "ch": "CHkk BBBB BCCC CCCC CCCC C",
    "cr": "CRkk BBBC CCCC CCCC CCCC CC",
    "cy": "CYkk BBBS SSSS CCCC CCCC CCCC CCCC",
    "cz": "CZkk BBBB SSSS SSCC CCCC CCCC",
    "de": "DEkk BBBB BBBB CCCC CCCC CC",
    "dk": "DKkk BBBB CCCC CCCC CC",
    "do": "DOkk BBBB CCCC CCCC CCCC CCCC CCCC",
    "ee": "EEkk BBSS CCCC CCCC CCCK",
    "es": "ESkk BBBB SSSS KKCC CCCC CCCC",
    "fi": "FIkk BBBB BBCC CCCC CK",
    "fo": "FOkk CCCC CCCC CCCC CC",
    "fr": "FRkk BBBB BSSS SSCC CCCC CCCC CKK",
    "gb": "GBkk BBBB SSSS SSCC CCCC CC",
    "ge": "GEkk BBCC CCCC CCCC CCCC CC",
    "gi": "GIkk BBBB CCCC CCCC CCCC CCC",
    "gl": "GLkk BBBB CCCC CCCC CC",
    "gr": "GRkk BBBS SSSC CCCC CCCC CCCC CCC",
    "gt": "GTkk BBBB MMTT CCCC CCCC CCCC CCCC",
    "hr": "HRkk BBBB BBBC CCCC CCCC C",
    "hu": "HUkk BBBS SSSC CCCC CCCC CCCC CCCC",
    "ie": "IEkk BBBB SSSS SSCC CCCC CC",
    "il": "ILkk BBBS SSCC CCCC CCCC CCC",
    "is": "ISkk BBBB SSCC CCCC FFFF FFFF FF",
    "it": "ITkk KBBB BBSS SSSC CCCC CCCC CCC",
    "jo": "JOkk BBBB SSSS CCCC CCCC CCCC CCCC CC",
    "kw": "KWkk BBBB CCCC CCCC CCCC CCCC CCCC CC",
    "kz": "KZkk BBBC CCCC CCCC CCCC",
    "lb": "LBkk BBBB CCCC CCCC CCCC CCCC CCCC",
    "li": "LIkk BBBB BCCC CCCC CCCC C",
    "lt": "LTkk BBBB BCCC CCCC CCCC",
    "lu": "LUkk BBBC CCCC CCCC CCCC",
    "lv": "LVkk BBBB CCCC CCCC CCCC C",
    "mc": "MCkk BBBB BSSS SSCC CCCC CCCC CKK",
    "md": "MDkk BBCC CCCC CCCC CCCC CCCC",
    "me": "MEkk BBBC CCCC CCCC CCCC KK",
    "mk": "MKkk BBBC CCCC CCCC CKK",
    "mr": "MRkk BBBB BSSS SSCC CCCC CCCC CKK",
    "mt": "MTkk BBBB SSSS SCCC CCCC CCCC CCCC CCC",
    "mu": "MUkk BBBB BBSS CCCC CCCC CCCC CCCC CC",
    "nl": "NLkk BBBB CCCC CCCC CC",
    "no": "NOkk BBBB CCCC CCK",
    "om": "OMkk BBBC CCCC CCCC CCCC CCC",
    "pk": "PKkk BBBB CCCC CCCC CCCC CCCC",
    "pl": "PLkk BBBS SSSK CCCC CCCC CCCC CCCC",
    "ps": "PSkk BBBB CCCC CCCC CCCC CCCC CCCC C",
    "pt": "PTkk BBBB SSSS CCCC CCCC CCCK K",
    "qa": "QAkk BBBB CCCC CCCC CCCC CCCC CCCC C",
    "ro": "ROkk BBBB CCCC CCCC CCCC CCCC",
    "rs": "RSkk BBBC CCCC CCCC CCCC KK",
    "sa": "SAkk BBCC CCCC CCCC CCCC CCCC",
    "se": "SEkk BBBB CCCC CCCC CCCC CCCC",
    "si": "SIkk BBSS SCCC CCCC CKK",
    "sk": "SKkk BBBB SSSS SSCC CCCC CCCC",
    "sm": "SMkk KBBB BBSS SSSC CCCC CCCC CCC",
    "tn": "TNkk BBSS SCCC CCCC CCCC CCCC",
    "tr": "TRkk BBBB BRCC CCCC CCCC CCCC CC",
    "ua": "UAkk BBBB BBCC CCCC CCCC CCCC CCCC C",
    "vg": "VGkk BBBB CCCC CCCC CCCC CCCC",
    "xk": "XKkk BBBB CCCC CCCC CCCC",
}
