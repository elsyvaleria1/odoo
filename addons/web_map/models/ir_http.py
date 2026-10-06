from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        if self.env.user._is_internal():
            result.update(
                map_box_token=self.env.registry.settings.get(
                    self.env, "web_map.token_map_box", False
                )
            )
        return result
