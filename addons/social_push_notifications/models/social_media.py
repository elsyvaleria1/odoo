from odoo import fields, models


class SocialMedia(models.Model):
    _inherit = "social.media"

    media_type = fields.Selection(
        selection_add=[("push_notifications", "Push Notifications")]
    )

    def _action_add_account(self):
        self.check_singleton()

        if self.media_type != "push_notifications":
            return super()._action_add_account()

        return None
