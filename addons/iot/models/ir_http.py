from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def lazy_session_info(self):
        res = super().lazy_session_info()
        if self.env.user._is_internal():
            res["iot_channel"] = self.env["iot.channel"].get_iot_channel()
        return res
