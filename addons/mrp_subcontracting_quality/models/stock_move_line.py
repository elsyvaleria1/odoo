from odoo import models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _unlink_quality_check(self) -> None:
        if self.env.user.partner_id.is_subcontractor and not self.env.su:
            super(StockMoveLine, self.sudo())._unlink_quality_check()
        else:
            super()._unlink_quality_check()
