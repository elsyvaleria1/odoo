from odoo.http import route

from odoo.addons.website_sale.controllers import main as website_sale_portal
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController


class WebsiteSaleRentingVariantController(WebsiteSaleVariantController):
    @route()
    def get_combination_info_website(self, *args, **kwargs):
        res = super().get_combination_info_website(*args, **kwargs)
        res["is_combination_possible"] = res.get(
            "is_combination_possible", True
        ) and res.get("is_plan_possible", True)
        if res.get("allow_one_time_sale") and not res.get("is_plan_possible"):
            res["is_combination_possible"] = True
        return res


class WebsiteSale(website_sale_portal.WebsiteSale):
    def _prepare_shop_payment_context(self, order, **kwargs):
        is_subscription = order.is_subscription or order.subscription_id.is_subscription
        return {
            **super()._prepare_shop_payment_context(order, **kwargs),
            "is_subscription": is_subscription,
        }
