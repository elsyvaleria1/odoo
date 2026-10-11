from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _amazon_create_activity_set_state(self, user_id, state_code) -> None:
        activity_message = self.env._(
            "This Amazon partner was created with an invalid state (%s); please set the correct"
            " state manually.",
            state_code,
        )
        self.activity_schedule(
            act_type_xmlid="mail.mail_activity_data_todo",
            user_id=user_id,
            note=activity_message,
        )
