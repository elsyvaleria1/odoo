from odoo import models


class MarketingTrace(models.Model):
    _inherit = "marketing.trace"

    def _get_exclusive_events(self):
        return super()._get_exclusive_events() | {"sms_bounce"}

    def _get_event_cancel_messages(self) -> dict:
        return {
            **super()._get_event_cancel_messages(),
            "sms_click": self.env._("Parent activity SMS clicked"),
            "sms_bounce": self.env._("Parent activity SMS bounced"),
        }
