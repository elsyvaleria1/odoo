from odoo import models


class EventEvent(models.Model):
    _inherit = "event.event"

    def action_mass_mailing_track_speakers(self):
        action = super().action_mass_mailing_track_speakers()
        action["view_id"] = self.env.ref(
            "mass_mailing_sms.mailing_mailing_view_form_mixed"
        ).id
        return action
