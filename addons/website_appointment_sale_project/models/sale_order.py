from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_confirm(self):
        self.line_ids.calendar_event_id.action_unarchive()
        self.line_ids.calendar_booking_ids._create_event_from_paid_booking()
        return super()._action_confirm()
