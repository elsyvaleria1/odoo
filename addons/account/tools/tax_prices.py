from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.api import Environment

    from odoo.addons.account.models.account_tax import AccountTax
    from odoo.addons.base.models.res_currency import ResCurrency


def price_from_tax_included_total(
    env: Environment, total: float, taxes: AccountTax, currency: ResCurrency
) -> float:
    taxes_res = taxes.with_context(force_price_include=True).compute_all(
        total, currency=currency
    )
    price = taxes_res["total_excluded"]
    for tax_res in taxes_res["taxes"]:
        tax = env["account.tax"].browse(tax_res["id"])
        if tax.price_include:
            price += tax_res["amount"]
    return price
