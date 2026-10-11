from typing import TYPE_CHECKING, Protocol, Self, cast

from odoo.http import request

if TYPE_CHECKING:
    from odoo.api import Environment
    from odoo.orm._typing import DomainType

    from ..models.website import Website


class QuickAddProduct(Protocol):
    env: Environment

    def check_singleton(self) -> Self: ...

    def filtered_domain(self, domain: DomainType) -> Self: ...

    def _get_contextual_price(self) -> float: ...


class WebsiteRequest(Protocol):
    website: Website


def can_show_quick_add(product: QuickAddProduct) -> bool:
    product.check_singleton()
    website = cast("Website", product.env["website"])
    if not product.filtered_domain(website._product_domain()):
        return False
    website_request = cast("WebsiteRequest", request)
    return bool(
        not website_request.website.prevent_zero_price_sale
        or product._get_contextual_price()
    )
