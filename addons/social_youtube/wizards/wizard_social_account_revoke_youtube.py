from urllib.parse import urlencode as url_encode

from odoo import fields, models
from odoo.exceptions import UserError


class WizardSocialAccountRevokeYoutube(models.TransientModel):

    _name = "wizard.social.account.revoke.youtube"
    _description = "Revoke YouTube Account"

    _YOUTUBE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

    account_id = fields.Many2one(
        comodel_name="social.account",
        readonly=True,
        required=True,
        ondelete="cascade",
    )

    def action_revoke(self):
        self.check_singleton()

        params = {"token": self.account_id.youtube_access_token}
        response = self.env["ir.egress"].request(
            "POST",
            f"{self._YOUTUBE_REVOKE_URL}?{url_encode(params)}",
            purpose="social_youtube",
            timeout=10,
        )

        if not response.ok:
            try:
                error = response.json()["error"]
            except ValueError, KeyError, TypeError:
                error = self.env._("Unknown")
            raise UserError(
                self.env._("Could not revoke your account.\nError: %s", error)
            )

        self.account_id.unlink()

        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "social.action_social_account"
        )
        action.update(
            {
                "context": {"no_breadcrumbs": True},
                "target": "main",
                "views": [(False, "list")],
            }
        )

        return action
