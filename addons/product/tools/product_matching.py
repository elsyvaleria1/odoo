from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.api import Environment

    from odoo.addons.base.models.res_company import ResCompany
    from odoo.addons.product.models.product_product import ProductProduct


def get_or_create_matching_product(
    env: Environment,
    company: ResCompany,
    internal_reference: str,
    default_xmlid: str,
    restore_default: Callable[[], ProductProduct],
    fallback: bool = True,
) -> ProductProduct:
    product = env["product.product"]
    if internal_reference:
        product = env["product.product"].search(
            [
                *env["product.product"]._get_domain_company_compatible(company),
                ("default_code", "=", internal_reference),
            ],
            limit=1,
        )
    if not product and fallback:
        product = env.ref(default_xmlid, raise_if_not_found=False) or restore_default()
    return product
