from odoo.exceptions import UserError
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.website_sale.controllers import delivery, main

_debug = DebugLog(__name__)


class WebsiteSaleExternalTaxCalculation(main.WebsiteSale):
    def _get_shop_payment_errors(self, order):
        errors = super()._get_shop_payment_errors(order)
        try:
            with _debug.perf(
                "external_taxes_payment_step", cr=order.env.cr, order=order
            ):
                order._get_and_set_external_taxes_on_eligible_records()
        except UserError as e:
            _debug.logic("external_tax_address_rejected", order=order, error=e)
            errors.append(
                (
                    request.env._("Validation Error"),
                    request.env._(
                        "This address does not appear to be valid. Please make sure it has been filled in correctly. Error details: %s",
                        e,
                    ),
                )
            )
        return errors

    def _prepare_shop_payment_context(self, order, **kwargs):
        res = super()._prepare_shop_payment_context(order, **kwargs)
        res["on_payment_step"] = True
        return res


class WebsiteSaleDelivery(delivery.Delivery):
    def _order_summary_values(self, order, **post):
        res = super()._order_summary_values(order, **post)
        try:
            with _debug.perf("external_taxes_summary", cr=order.env.cr, order=order):
                order._get_and_set_external_taxes_on_eligible_records()
        except UserError as e:
            _debug.logic("external_tax_summary_failed", order=order, error=e)
            res["external_tax_error"] = str(e)
        return res
