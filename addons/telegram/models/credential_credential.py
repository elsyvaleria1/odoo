from odoo import models


class CredentialCredential(models.Model):
    _inherit = "credential.credential"

    def _get_display_name_visible_ids(self) -> set[int]:
        # a bot's token credential follows the bot's company behind the
        # credentials' company guard: whoever reads the bot reads its name,
        # never the secret
        visible = super()._get_display_name_visible_ids()
        bots = self.env["telegram.bot"]
        if not bots.has_access("read"):
            return visible
        bots = bots.search([("credential_id", "in", self.ids)])
        return visible | set(bots.credential_id._ids)
