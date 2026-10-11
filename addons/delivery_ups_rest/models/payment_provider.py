from odoo import api, models

from odoo.addons.payment import utils as payment_utils


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    @api.model
    def _get_compatible_providers(
        self, *args, sale_order_id=None, report=None, **kwargs
    ):
        compatible_providers = super()._get_compatible_providers(
            *args, sale_order_id=sale_order_id, report=report, **kwargs
        )

        sale_order = self.env["sale.order"].browse(sale_order_id).exists()
        if (
            sale_order.carrier_id.delivery_type == "ups_rest"
            and sale_order.carrier_id.allow_cash_on_delivery
        ):
            unfiltered_providers = compatible_providers
            compatible_providers = compatible_providers.filtered(
                lambda p: p.custom_mode == "cash_on_delivery"
            )
            payment_utils.add_to_report(
                report,
                unfiltered_providers - compatible_providers,
                available=False,
                reason=self.env._(
                    "UPS provider is configured to use only Collect on Delivery."
                ),
            )

        return compatible_providers
