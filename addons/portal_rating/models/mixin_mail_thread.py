from odoo import models
from odoo.fields import Domain


class MixinMailThread(models.AbstractModel):
    _inherit = "mixin.mail.thread"

    def _get_domain_portal_message_non_empty(self):
        return super()._get_domain_portal_message_non_empty() | Domain(
            "rating_value", "!=", False
        )
