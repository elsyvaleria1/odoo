from odoo import http
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.web.controllers.utils import fragments_or_redirect
from odoo.addons.website_sale.controllers.delivery import Delivery
from odoo.addons.website_sale.controllers.main import WebsiteSale

_debug = DebugLog(__name__)


class MondialRelay(http.Controller):
    @http.route(
        ["/website_sale_mondialrelay/update_shipping"],
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
    )
    def mondial_relay_update_shipping(self, **data):
        order_sudo = request.cart

        if not order_sudo or order_sudo._is_anonymous_cart():
            _debug.logic("pickup_point_refused", reason="anonymous_cart")
            raise AccessDenied(
                request.env._("A customer is required before selecting a pickup point.")
            )
        if not order_sudo.carrier_id.is_mondialrelay:
            _debug.logic(
                "pickup_point_refused",
                reason="not_mondialrelay",
                carrier=order_sudo.carrier_id.id,
            )
            raise UserError(
                request.env._("Select a Mondial Relay delivery method first.")
            )
        address_values = self._parse_relay_address(data)

        countries = order_sudo.carrier_id.country_ids
        if countries and address_values["country_code"].upper() not in countries.mapped(
            "code"
        ):
            raise UserError(
                request.env._(
                    "The pickup point country is not allowed for this delivery carrier."
                )
            )

        partner_shipping = order_sudo.partner_id.sudo()._mondialrelay_search_or_create(
            address_values
        )
        if order_sudo.partner_shipping_id != partner_shipping:
            order_sudo.partner_shipping_id = partner_shipping

        # the new address moves the delivery rates and the addresses shown:
        # the checkout is loaded again, as it was after the old JSON answer
        return fragments_or_redirect(
            request.env, "/shop/checkout", redirect="/shop/checkout"
        )

    def _parse_relay_address(self, data):
        fields = {
            "id": "ID",
            "name": "Nom",
            "street": "Adresse1",
            "zip": "CP",
            "city": "Ville",
            "country_code": "Pays",
        }
        values = {}
        for field, source in fields.items():
            value = data.get(source)
            if field in {"id", "zip"} and type(value) is int:
                value = str(value)
            if not isinstance(value, str) or not value.strip():
                raise UserError(
                    request.env._(
                        "The pickup point is missing valid address information."
                    )
                )
            values[field] = value.strip()
        street2 = data.get("Adresse2") or ""
        if not isinstance(street2, str):
            raise UserError(
                request.env._("The pickup point is missing valid address information.")
            )
        values["street2"] = street2.strip()
        values["country_code"] = values["country_code"][:2].lower()
        return values


class WebsiteSaleMondialrelay(WebsiteSale):
    def _prepare_address_update(self, *args, **kwargs):
        partner_sudo, _address_type = super()._prepare_address_update(*args, **kwargs)

        if partner_sudo and partner_sudo.is_mondialrelay:
            raise UserError(
                request.env._("You cannot edit the address of a Point Relais®.")
            )

        return partner_sudo, _address_type

    def _is_delivery_address_complete(self, partner_sudo) -> bool:
        if partner_sudo.is_mondialrelay:
            return True
        return super()._is_delivery_address_complete(partner_sudo)


class WebsiteSaleDeliveryMondialrelay(Delivery):
    def _order_summary_values(self, order, **post):
        res = super()._order_summary_values(order, **post)
        if order.carrier_id.is_mondialrelay:
            res["mondial_relay"] = {
                "brand": order.carrier_id.mondialrelay_brand,
                "col_liv_mod": order.carrier_id.mondialrelay_packagetype,
                "partner_zip": order.partner_shipping_id.zip,
                "partner_country_code": order.partner_shipping_id.country_id.code.upper(),
                "allowed_countries": ",".join(
                    order.carrier_id.country_ids.mapped("code")
                ).upper(),
            }
            if order.partner_shipping_id.is_mondialrelay:
                res["mondial_relay"]["current"] = "%s-%s" % (
                    res["mondial_relay"]["partner_country_code"],
                    order.partner_shipping_id.ref.removeprefix("MR#"),
                )

        return res
