from collections.abc import MutableMapping
from typing import TypedDict

from odoo.addons.account_edi_ubl_cii.models.account_edi_common import FloatFmt


class UblPriceValues(TypedDict):
    price_amount_currency: float


class UblPriceBaseLine(TypedDict):
    _ubl_values: UblPriceValues


class UblLinePriceValues(TypedDict):
    base_line: UblPriceBaseLine
    currency_name: str


def update_ubl_line_price_node(
    line_node: MutableMapping[str, object], vals: UblLinePriceValues
) -> None:
    base_line = vals["base_line"]
    ubl_values = base_line["_ubl_values"]
    line_node["cac:Price"] = {
        "cbc:PriceAmount": {
            "_text": FloatFmt(ubl_values["price_amount_currency"], min_dp=1, max_dp=6),
            "currencyID": vals["currency_name"],
        },
    }


def update_ubl_discount_node(discount_node: MutableMapping[str, object]) -> None:
    discount_node["cbc:AllowanceChargeReason"] = None
    discount_node["cbc:MultiplierFactorNumeric"] = None
    discount_node["cbc:BaseAmount"] = None
