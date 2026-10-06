from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHelpdeskTicketCreateCoupon(models.TransientModel):
    _inherit = "wizard.helpdesk.ticket.create.coupon"

    def action_coupon_generate_share(self):
        self.check_singleton()
        coupon = (
            self.env["loyalty.card"]
            .sudo()
            .create(
                {
                    "partner_id": self.ticket_id.partner_id.id,
                    "program_id": self.program.id,
                    "points": self.points_granted,
                    "expiration_date": self.valid_until,
                }
            )
        )
        self.ticket_id.coupon_ids |= coupon
        _debug.lifecycle(
            "coupon_granted",
            ticket=self.ticket_id,
            coupon=coupon,
            program=self.program,
            points=self.points_granted,
            valid_until=self.valid_until,
        )
        return self.env["wizard.loyalty.program.share"].create_share_action(
            coupon=coupon
        )
