from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _create_delivery_line(self, carrier, price_unit):
        res = super()._create_delivery_line(carrier, price_unit)
        if carrier.delivery_type == "ups" and carrier.ups_bill_my_account:
            res.name = "[UPS] UPS Billing will remain to the customer"
        return res

    partner_ups_carrier_account = fields.Char(
        string="UPS account number",
        compute="_compute_ups_carrier_account",
        inverse="_inverse_ups_carrier_account",
        copy=False,
        readonly=False,
    )
    ups_bill_my_account = fields.Boolean(
        related="carrier_id.ups_bill_my_account",
        readonly=True,
    )

    @api.depends("partner_shipping_id")
    def _compute_ups_carrier_account(self) -> None:
        for order in self:
            order.partner_ups_carrier_account = order.partner_shipping_id.with_company(
                order.company_id
            ).property_ups_carrier_account

    def _inverse_ups_carrier_account(self) -> None:
        for order in self:
            order.partner_shipping_id.sudo().with_company(
                order.company_id
            ).property_ups_carrier_account = order.partner_ups_carrier_account

    def _action_confirm(self):
        if any(
            order.carrier_id.ups_bill_my_account
            and not order.partner_ups_carrier_account
            for order in self
        ):
            raise UserError(self.env._("You must enter an UPS account number."))
        return super()._action_confirm()
