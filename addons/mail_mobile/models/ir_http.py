from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        if self.env.user._is_internal():
            result.update(
                ocn_token_key=self.env.user.partner_id.ocn_token,
                fcm_project_id=self.env.registry.settings.get(
                    self.env, "odoo_ocn.project_id", False
                ),
                inbox_action=self.env.ref("mail.action_discuss").id,
            )
        return result
