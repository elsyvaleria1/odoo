from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.addons.account.models.account_tax import AccountTax
    from odoo.addons.base.models.res_currency import ResCurrency


def price_from_tax_included_total(
    total: float, taxes: AccountTax, currency: ResCurrency
) -> float:
    taxes_res = taxes.with_context(force_price_include=True).compute_all(
        total, currency=currency
    )
    return taxes_res["total_excluded"] + sum(
        tax_res["amount"] for tax_res in taxes_res["taxes"] if tax_res["price_include"]
    )
