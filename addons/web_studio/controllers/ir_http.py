from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()

        if result["is_system"]:
            # necessary keys for Studio
            result["dbuuid"] = self.env.registry.settings.get(
                self.env, "database.uuid", False
            )
            result["multi_lang"] = len(self.env["res.lang"].get_installed()) > 1

        return result
