from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.website_sale.controllers import main

_debug = DebugLog(__name__)


class WebsiteSale(main.WebsiteSale):
    @http.route(
        "/shop/ups_check_service_type",
        type="jsonrpc",
        auth="public",
        website=True,
        sitemap=False,
    )
    def ups_check_service_type_is_available(self, **post):
        return request.env["sale.order"].sudo().check_ups_service_type(post)

    @http.route(
        "/shop/property_ups_carrier_account/set",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def set_property_ups_carrier_account(self, **post):
        order_sudo = request.cart

        _debug.lifecycle(
            "set_ups_account",
            order=order_sudo,
            carrier=order_sudo.carrier_id,
            bill_my_account=order_sudo.carrier_id.ups_bill_my_account,
            provided=bool(post.get("property_ups_carrier_account")),
        )
        if order_sudo.carrier_id.ups_bill_my_account and post.get(
            "property_ups_carrier_account"
        ):
            order_sudo.write(
                {
                    "partner_ups_carrier_account": post["property_ups_carrier_account"],
                }
            )
        return request.redirect("/shop/checkout")

    @http.route(
        "/shop/property_ups_carrier_account/unset",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def reset_property_ups_carrier_account(self, **post):
        order_sudo = request.cart
        _debug.lifecycle(
            "unset_ups_account",
            order=order_sudo,
            had_account=bool(order_sudo.partner_ups_carrier_account),
        )
        if order_sudo.partner_ups_carrier_account:
            order_sudo.write(
                {
                    "partner_ups_carrier_account": False,
                }
            )
        return request.redirect("/shop/checkout")
