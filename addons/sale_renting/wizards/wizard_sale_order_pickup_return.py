from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSaleOrderPickupReturn(models.TransientModel):
    _name = "wizard.sale.order.pickup.return"
    _description = "Pick-up/Return products"

    order_id = fields.Many2one(
        comodel_name="sale.order",
        required=True,
        ondelete="cascade",
    )
    rental_wizard_line_ids = fields.One2many(
        comodel_name="wizard.sale.order.pickup.return.line",
        inverse_name="rental_order_wizard_id",
    )
    status = fields.Selection(
        selection=[
            ("pickup", "Pickup"),
            ("return", "Return"),
        ]
    )
    is_late = fields.Boolean(compute="_compute_is_late")

    @api.depends(
        "order_id.is_late",
        "order_id.next_action_date",
        "order_id.company_id.min_extra_hour",
    )
    def _compute_is_late(self) -> None:
        """Include the minimum time buffer allowed before an extra cost is added to the order."""
        now = fields.Datetime.now()
        for wizard in self:
            min_extra_hours = relativedelta(
                hours=wizard.order_id.company_id.min_extra_hour
            )
            wizard.is_late = (
                wizard.order_id.is_late
                and wizard.order_id.next_action_date + min_extra_hours < now
            )

    @api.onchange("order_id")
    def _update_wizard_lines(self) -> None:
        """Use Wizard lines to set by default the pickup/return value
        to the total pickup/return value expected"""
        rental_lines_ids = self.env.context.get("order_line_ids", [])
        rental_lines_to_process = self.env["sale.order.line"].browse(rental_lines_ids)

        # generate line values
        if rental_lines_to_process:
            lines_values = [
                self.env[
                    "wizard.sale.order.pickup.return.line"
                ]._prepare_wizard_line_vals(line, self.status)
                for line in rental_lines_to_process
            ]

            self.rental_wizard_line_ids = [Command.set([])] + [
                Command.create(vals) for vals in lines_values
            ]

    def apply(self):
        """Apply the wizard modifications to the SaleOrderLine(s).

        And logs the rental infos in the SaleOrder chatter
        """
        for wizard in self:
            msg = wizard.rental_wizard_line_ids._apply()
            if msg:
                for key, value in wizard._fields["status"]._description_selection(
                    wizard.env
                ):
                    if key == wizard.status:
                        translated_status = value
                        break

                msg = Markup("<b>%s</b>:<ul>%s</ul>") % (translated_status, msg)
                wizard.order_id.message_post(body=msg)
