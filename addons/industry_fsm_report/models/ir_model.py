from odoo import api, models
from odoo.db.schema import column_exists


class IrModel(models.Model):
    _inherit = "ir.model"

    @api.ondelete(at_uninstall=True)
    def _unlink_if_uninstalling(self) -> None:
        if column_exists(self.env.cr, "worksheet_template", "model_id"):
            self.env["worksheet.template"].with_context(active_test=False).search(
                [("model_id", "in", self.ids)]
            ).unlink()
