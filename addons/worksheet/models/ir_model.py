from odoo import api, models


class IrModel(models.Model):
    _inherit = "ir.model"

    @api.ondelete(at_uninstall=False)
    def _unlink_worksheet_templates(self) -> None:
        self.env["worksheet.template"].with_context(active_test=False).search(
            [("model_id", "in", self.ids)]
        ).unlink()
