from odoo import models
from odoo.api import ValuesType

from ..tools.authority import keeping


class CredentialCredential(models.Model):
    _inherit = "credential.credential"

    def write(self, vals: ValuesType) -> bool:
        result = super().write(vals)
        if "active" in vals:
            bots = (
                keeping(self.env["telegram.bot"])
                .with_context(active_test=False)
                .search([("credential_id", "in", self.ids)])
            )
            if bots:
                bots._handle_on_air_change()
        return result

    def _get_display_name_visible_ids(self) -> set[int]:
        visible = super()._get_display_name_visible_ids()
        bots = self.env["telegram.bot"]
        if not bots.has_access("read"):
            return visible
        bots = bots.search([("credential_id", "in", self.ids)])
        return visible | set(bots.credential_id._ids)
