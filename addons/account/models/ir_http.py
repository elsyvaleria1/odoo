from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def lazy_session_info(self):
        res = super().lazy_session_info()
        res["show_sale_receipts"] = self.env.registry.settings.get(
            self.env, "account.show_sale_receipts", False
        )
        return res
